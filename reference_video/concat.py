"""
Stitches the generated per-shot videos together into one file, in the
order a timeline file lists them (not alphabetical filename order).

Takes either scenes.json (plain shot list, all generated via fal.ai) or
timeline.json (a mix of {"type": "scene", "id": ...} and
{"type": "title_card", "text": ..., "duration": ...} entries). Title
cards are generated locally for free (PIL + ffmpeg), no AI model call,
matched to the detected resolution of the actual scene clips.

Requires ffmpeg installed locally (brew install ffmpeg on Mac) and Pillow
(in requirements.txt). Uses stream copy (fast, no re-encode) for the final
concat, which requires every clip to share the same resolution/codec,
that's why it checks resolutions first and warns rather than producing a
broken output if they don't match.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
]


def get_resolution(path: Path):
    try:
        from pymediainfo import MediaInfo
        for track in MediaInfo.parse(str(path)).tracks:
            if track.track_type == "Video":
                return (track.width, track.height)
    except Exception:
        pass
    return None


def make_title_card(text: str, duration: float, resolution: tuple, out_path: Path):
    """Renders a black card with centered white text, held for `duration` seconds,
    at the given (width, height). No AI model call, generated locally for free."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = resolution
    img = Image.new("RGB", (width, height), "black")
    draw = ImageDraw.Draw(img)

    font = None
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                font = ImageFont.truetype(candidate, size=height // 10)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((width - text_w) / 2, (height - text_h) / 2), text, fill="white", font=font)

    png_path = out_path.with_suffix(".png")
    img.save(png_path)

    subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-i", str(png_path), "-t", str(duration),
         "-r", "24", "-pix_fmt", "yuv420p", str(out_path)],
        check=True, capture_output=True,
    )
    png_path.unlink()


def load_timeline(path: Path):
    """Accepts either a plain scenes.json (list of shots) or a timeline.json
    (list of {"type": ...} entries). Normalizes to the latter shape."""
    data = json.loads(path.read_text())
    if data and "type" in data[0]:
        return data
    return [{"type": "scene", "id": s["id"]} for s in data]


def main():
    parser = argparse.ArgumentParser(description="Concatenate generated scene videos (and title cards) in order")
    parser.add_argument("timeline_file", help="Path to scenes.json or timeline.json (defines the order)")
    parser.add_argument("--out", default=str(OUTPUT_DIR / "full_video.mp4"), help="Output file path")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("ffmpeg not found. Install it first: brew install ffmpeg")
        sys.exit(1)

    timeline = load_timeline(Path(args.timeline_file))

    scene_clips = []
    missing = []
    for entry in timeline:
        if entry["type"] != "scene":
            continue
        scene_id = entry["id"]
        final = OUTPUT_DIR / f"{scene_id}_final.mp4"
        video = OUTPUT_DIR / f"{scene_id}_video.mp4"
        path = final if final.exists() else (video if video.exists() else None)
        if path is None:
            missing.append(scene_id)
        else:
            scene_clips.append(path)

    if missing:
        print(f"Warning: no output found for {len(missing)} shot(s), skipping: {', '.join(missing)}")
    if not scene_clips:
        print("No clips found to concatenate. Run generate.py first.")
        sys.exit(1)

    resolutions = {get_resolution(p) for p in scene_clips}
    resolutions.discard(None)
    if len(resolutions) > 1:
        print(f"Warning: clips have different resolutions ({resolutions}), stream-copy concat will "
              f"likely fail or produce a broken file. Regenerate the mismatched shots at the same "
              f"--resolution first. Per-shot resolutions:")
        for p in scene_clips:
            print(f"  {p.stem}: {get_resolution(p)}")
        sys.exit(1)
    resolution = next(iter(resolutions))

    title_card_dir = OUTPUT_DIR / "_title_cards"
    title_card_dir.mkdir(exist_ok=True)
    generated_cards = []

    list_file = OUTPUT_DIR / "_concat_list.txt"
    with open(list_file, "w") as f:
        card_i = 0
        for entry in timeline:
            if entry["type"] == "scene":
                scene_id = entry["id"]
                final = OUTPUT_DIR / f"{scene_id}_final.mp4"
                video = OUTPUT_DIR / f"{scene_id}_video.mp4"
                path = final if final.exists() else video
                if not path.exists():
                    continue
                f.write(f"file '{path.resolve()}'\n")
                print(f"  scene: {scene_id}")
            elif entry["type"] == "title_card":
                card_i += 1
                card_path = title_card_dir / f"card_{card_i}.mp4"
                make_title_card(entry["text"], entry.get("duration", 1.5), resolution, card_path)
                generated_cards.append(card_path)
                f.write(f"file '{card_path.resolve()}'\n")
                print(f"  title card: \"{entry['text']}\" ({entry.get('duration', 1.5)}s)")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", args.out],
        check=True,
    )
    list_file.unlink()
    for card in generated_cards:
        card.unlink()
    title_card_dir.rmdir()
    print(f"\nSaved -> {args.out}")


if __name__ == "__main__":
    main()
