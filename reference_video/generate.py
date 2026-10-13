"""
Standalone batch script: generate multiple scenes via fal.ai reference-to-video,
with optional ElevenLabs voice + VEED lipsync per scene.

Separate from the Else Clips app on purpose: different style, different subject,
no review UI, no shots.json/state.json. Scenes go in, videos come out.

Scene schema (see scenes.json):
{
  "id": "s01_...",
  "prompt": "...",
  "reference_images": ["refs/daniel_face.jpg", "refs/daniel_body.jpg", ...],
  "dialogue": [                      # optional, omit for a silent shot
    {"character": "daniel", "voice_id": "...", "line": "...", "lipsync": true}
  ]
}
Lipsync only runs when a shot has exactly one dialogue entry with "lipsync": true
(same rule as the main app: can't lipsync a shot with two speakers at once).
Every dialogue entry still gets its voice generated even when lipsync is off,
so off-screen/phone lines are available as separate audio to mix in later.

NOTE: the exact argument names for the reference-to-video endpoint below
(REFERENCE_TO_VIDEO_ENDPOINT, and "reference_image_urls" in generate_scene_video)
are based on fal.ai's documented pattern for this model family, not a live
test against the endpoint. Check the model's page on fal.ai before your
first real run in case the parameter name differs, that's a one-line fix
here if so.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fal_client
import pipeline

REFERENCE_TO_VIDEO_ENDPOINT = "minimax/h3-max/reference-to-video"
RESOLUTION = "768p"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
REFS_DIR = Path(__file__).resolve().parent


def generate_scene_video(prompt: str, reference_image_paths: list, resolution: str = RESOLUTION) -> str:
    """Uploads reference images, generates one scene, returns the fal-hosted result URL."""
    if not pipeline.FAL_KEY:
        raise RuntimeError("FAL_KEY not set, check your .env")
    image_urls = [pipeline.upload_local_file(str(REFS_DIR / p)) for p in reference_image_paths]
    arguments = {
        "prompt": prompt,
        "reference_image_urls": image_urls,
        "resolution": resolution,
    }
    result = fal_client.subscribe(
        REFERENCE_TO_VIDEO_ENDPOINT,
        arguments=arguments,
        with_logs=True,
        on_queue_update=lambda u: [print(l["message"]) for l in getattr(u, "logs", [])],
    )
    return result["video"]["url"]


def run_scene(scene: dict) -> dict:
    scene_id = scene["id"]
    video_url = generate_scene_video(scene["prompt"], scene["reference_images"])
    video_path = OUTPUT_DIR / f"{scene_id}_video.mp4"
    pipeline.download_to_file(video_url, str(video_path))

    dialogue = scene.get("dialogue", [])
    voice_paths = []
    for i, entry in enumerate(dialogue, start=1):
        voice_path = OUTPUT_DIR / f"{scene_id}_voice{i}_{entry['character']}.mp3"
        pipeline.generate_voice(entry["line"], entry["voice_id"], str(voice_path))
        voice_paths.append(voice_path)

    final_path = video_path
    if len(dialogue) == 1 and dialogue[0].get("lipsync", True):
        audio_url = pipeline.upload_local_file(str(voice_paths[0]))
        video_url_for_sync = pipeline.upload_local_file(str(video_path))
        synced_url = pipeline.lipsync(video_url_for_sync, audio_url)
        final_path = OUTPUT_DIR / f"{scene_id}_final.mp4"
        pipeline.download_to_file(synced_url, str(final_path))

    return {"id": scene_id, "status": "ok", "video": str(video_path),
            "voices": [str(p) for p in voice_paths], "final": str(final_path)}


def run_batch(scenes: list, dry_run: bool = False) -> list:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for i, scene in enumerate(scenes, start=1):
        scene_id = scene.get("id") or f"scene_{i:02d}"
        n_lines = len(scene.get("dialogue", []))
        print(f"[{i}/{len(scenes)}] {scene_id} ({n_lines} line{'s' if n_lines != 1 else ''}): {scene['prompt'][:70]}")
        if dry_run:
            print("  (dry run, skipped)")
            continue
        try:
            results.append(run_scene(scene))
            print(f"  saved -> {results[-1]['final']}")
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({"id": scene_id, "status": "failed", "error": str(e)})
    return results


def main():
    parser = argparse.ArgumentParser(description="Batch-generate scenes via fal.ai reference-to-video")
    parser.add_argument("scenes_file", help="Path to a JSON file holding a list of scenes")
    parser.add_argument("--dry-run", action="store_true", help="Print what would run without calling any API")
    parser.add_argument("--only", help="Comma-separated scene ids to run instead of the whole file, "
                                        "e.g. --only s04_begging")
    args = parser.parse_args()

    scenes = json.loads(Path(args.scenes_file).read_text())
    if args.only:
        wanted = set(args.only.split(","))
        scenes = [s for s in scenes if s["id"] in wanted]
        missing = wanted - {s["id"] for s in scenes}
        if missing:
            print(f"Warning: these ids weren't found in {args.scenes_file}: {', '.join(missing)}")
        if not scenes:
            print("Nothing to run.")
            return

    results = run_batch(scenes, dry_run=args.dry_run)

    ok = sum(1 for r in results if r["status"] == "ok")
    failed = sum(1 for r in results if r["status"] == "failed")
    if args.dry_run:
        print(f"\nDry run: {len(scenes)} scenes would run")
    else:
        print(f"\nDone: {ok} succeeded, {failed} failed")


if __name__ == "__main__":
    main()
