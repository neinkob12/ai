"""
Stitches the generated per-shot videos together into one file, in the
order scenes.json lists them (not alphabetical filename order).

Requires ffmpeg installed locally (brew install ffmpeg on Mac). Uses
stream copy (fast, no re-encode), which requires every clip to share the
same resolution/codec, that's why it checks resolutions first and warns
rather than producing a broken output if they don't match.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def get_resolution(path: Path):
    try:
        from pymediainfo import MediaInfo
        for track in MediaInfo.parse(str(path)).tracks:
            if track.track_type == "Video":
                return (track.width, track.height)
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Concatenate generated scene videos in script order")
    parser.add_argument("scenes_file", help="Path to the scenes JSON file (defines the order)")
    parser.add_argument("--out", default=str(OUTPUT_DIR / "full_video.mp4"), help="Output file path")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("ffmpeg not found. Install it first: brew install ffmpeg")
        sys.exit(1)

    scenes = json.loads(Path(args.scenes_file).read_text())

    clips = []
    missing = []
    for scene in scenes:
        scene_id = scene["id"]
        final = OUTPUT_DIR / f"{scene_id}_final.mp4"
        video = OUTPUT_DIR / f"{scene_id}_video.mp4"
        path = final if final.exists() else (video if video.exists() else None)
        if path is None:
            missing.append(scene_id)
        else:
            clips.append((scene_id, path))

    if missing:
        print(f"Warning: no output found for {len(missing)} shot(s), skipping: {', '.join(missing)}")
    if not clips:
        print("No clips found to concatenate. Run generate.py first.")
        sys.exit(1)

    resolutions = {get_resolution(p) for _, p in clips}
    resolutions.discard(None)
    if len(resolutions) > 1:
        print(f"Warning: clips have different resolutions ({resolutions}), stream-copy concat will "
              f"likely fail or produce a broken file. Regenerate the mismatched shots at the same "
              f"--resolution first. Per-shot resolutions:")
        for scene_id, p in clips:
            print(f"  {scene_id}: {get_resolution(p)}")
        sys.exit(1)

    list_file = OUTPUT_DIR / "_concat_list.txt"
    with open(list_file, "w") as f:
        for scene_id, path in clips:
            f.write(f"file '{path.resolve()}'\n")

    print(f"Concatenating {len(clips)} clips in this order:")
    for scene_id, _ in clips:
        print(f"  {scene_id}")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", args.out],
        check=True,
    )
    list_file.unlink()
    print(f"\nSaved -> {args.out}")


if __name__ == "__main__":
    main()
