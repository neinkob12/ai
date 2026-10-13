"""
Standalone batch script: generate multiple scenes via fal.ai reference-to-video.

Separate from the Else Clips app on purpose: different style, different subject,
no review UI, no shots.json/state.json. Scenes go in, videos come out.

NOTE: the exact argument names for the reference-to-video endpoint below
(REFERENCE_TO_VIDEO_ENDPOINT, and "reference_image_urls" in generate_scene)
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
from pipeline import FAL_KEY, download_to_file, upload_local_file

REFERENCE_TO_VIDEO_ENDPOINT = "fal-ai/minimax/h3-max/reference-to-video"
RESOLUTION = "768p"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def generate_scene(prompt: str, reference_image_paths: list, resolution: str = RESOLUTION) -> str:
    """Uploads reference images, generates one scene, returns the fal-hosted result URL."""
    if not FAL_KEY:
        raise RuntimeError("FAL_KEY not set, check your .env")
    image_urls = [upload_local_file(p) for p in reference_image_paths]
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


def run_batch(scenes: list, dry_run: bool = False) -> list:
    """scenes: list of {"id": str, "prompt": str, "reference_images": [path, ...]}"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for i, scene in enumerate(scenes, start=1):
        scene_id = scene.get("id") or f"scene_{i:02d}"
        print(f"[{i}/{len(scenes)}] {scene_id}: {scene['prompt'][:80]}")
        if dry_run:
            print("  (dry run, skipped)")
            continue
        try:
            video_url = generate_scene(scene["prompt"], scene["reference_images"])
            out_path = OUTPUT_DIR / f"{scene_id}.mp4"
            download_to_file(video_url, str(out_path))
            print(f"  saved -> {out_path}")
            results.append({"id": scene_id, "status": "ok", "path": str(out_path)})
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({"id": scene_id, "status": "failed", "error": str(e)})
    return results


def main():
    parser = argparse.ArgumentParser(description="Batch-generate scenes via fal.ai reference-to-video")
    parser.add_argument("scenes_file", help="Path to a JSON file holding a list of scenes")
    parser.add_argument("--dry-run", action="store_true", help="Print what would run without calling the API")
    args = parser.parse_args()

    scenes = json.loads(Path(args.scenes_file).read_text())
    results = run_batch(scenes, dry_run=args.dry_run)

    ok = sum(1 for r in results if r["status"] == "ok")
    failed = sum(1 for r in results if r["status"] == "failed")
    skipped = len(results) - ok - failed if not args.dry_run else len(scenes)
    print(f"\nDone: {ok} succeeded, {failed} failed" + (f", {skipped} skipped (dry run)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
