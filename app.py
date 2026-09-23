import os
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

import pipeline
import store
from config.settings import ASSETS_DIR, OUTPUT_DIR

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "else-clips-dev")


def _shot_output_dir(shot_id, stage):
    d = OUTPUT_DIR / shot_id / stage
    d.mkdir(parents=True, exist_ok=True)
    return d


def _relative_to_output(path: Path) -> str:
    return path.relative_to(OUTPUT_DIR).as_posix()


@app.route("/")
def index():
    shots = store.load_shots()
    state_by_id = store.load_state()
    rows = []
    for shot in shots:
        s = state_by_id.get(shot["id"], {})
        rows.append({
            "id": shot["id"],
            "title": shot["title"],
            "locked": s.get("locked", False),
            "accepted_voice": s.get("accepted_voice"),
            "accepted_video": s.get("accepted_video"),
        })
    return render_template("index.html", shots=rows)


@app.route("/shot/<shot_id>")
def shot_detail(shot_id):
    data = store.get_shot_state(shot_id)
    if data is None:
        abort(404)
    shot, state = data["shot"], data["state"]
    lipsync_eligible = len(shot["dialogue"]) == 1
    return render_template(
        "shot.html",
        shot=shot,
        state=state,
        locations=store.load_locations(),
        characters=store.load_characters(),
        lipsync_eligible=lipsync_eligible,
    )


@app.route("/shot/new", methods=["POST"])
def new_shot():
    title = request.form.get("title", "").strip()
    if not title:
        flash("Give the new shot a title.")
        return redirect(url_for("index"))
    shot_id = store.create_shot(title)
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/delete", methods=["POST"])
def delete_shot(shot_id):
    store.delete_shot(shot_id)
    flash(f'Deleted "{shot_id}".')
    return redirect(url_for("index"))


@app.route("/shot/<shot_id>/title", methods=["POST"])
def update_title(shot_id):
    title = request.form.get("title", "").strip()
    if title:
        store.update_shot_title(shot_id, title)
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/characters", methods=["POST"])
def update_characters(shot_id):
    store.update_shot_characters(shot_id, request.form.getlist("characters"))
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/in_else", methods=["POST"])
def update_in_else(shot_id):
    store.update_shot_in_else(shot_id, "in_else" in request.form)
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/unlock", methods=["POST"])
def unlock(shot_id):
    store.unlock_shot(shot_id)
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/prompt", methods=["POST"])
def update_prompt(shot_id):
    store.update_working_prompt(shot_id, request.form["visual_prompt"])
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/dialogue/<int:index>", methods=["POST"])
def update_dialogue(shot_id, index):
    store.update_working_dialogue_line(shot_id, index, request.form["line"])
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/dialogue/add", methods=["POST"])
def add_dialogue(shot_id):
    character = request.form.get("character") or None
    line = request.form.get("line", "").strip()
    if not line:
        flash("Dialogue line can't be empty.")
        return redirect(url_for("shot_detail", shot_id=shot_id))
    store.add_dialogue_line(shot_id, character, line)
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/dialogue/<int:index>/remove", methods=["POST"])
def remove_dialogue(shot_id, index):
    store.remove_dialogue_line(shot_id, index)
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/duplicate", methods=["POST"])
def duplicate_shot(shot_id):
    new_id = store.duplicate_shot(shot_id)
    if new_id is None:
        abort(404)
    return redirect(url_for("shot_detail", shot_id=new_id))


@app.route("/shot/<shot_id>/move/<direction>", methods=["POST"])
def move_shot(shot_id, direction):
    store.move_shot(shot_id, direction)
    return redirect(url_for("index"))


@app.route("/shot/<shot_id>/voice/generate", methods=["POST"])
def generate_voice_route(shot_id):
    data = store.get_shot_state(shot_id)
    shot, state = data["shot"], data["state"]
    dialogue = state["working_dialogue"]
    if not dialogue:
        flash("This shot has no dialogue to voice.")
        return redirect(url_for("shot_detail", shot_id=shot_id))

    entry = dialogue[0]
    voice_id = store.resolve_voice_id(entry.get("character"), entry.get("voice_id"))
    if not voice_id:
        flash("No voice_id resolved for this line. Set one on the character in "
              "characters.json, or as a per-line override.")
        return redirect(url_for("shot_detail", shot_id=shot_id))

    out_dir = _shot_output_dir(shot_id, "voice")
    version = len(state["voice_takes"]) + 1
    out_path = out_dir / f"v{version}.mp3"
    try:
        pipeline.generate_voice(entry["line"], voice_id, str(out_path))
    except Exception as e:
        flash(f"Voice generation failed: {e}")
        return redirect(url_for("shot_detail", shot_id=shot_id))

    store.add_voice_take(
        shot_id, _relative_to_output(out_path), entry["line"], voice_id, entry.get("character")
    )
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/voice/accept/<int:version>", methods=["POST"])
def accept_voice(shot_id, version):
    store.accept_voice_take(shot_id, version)
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/voice/delete/<int:version>", methods=["POST"])
def delete_voice_take(shot_id, version):
    store.delete_voice_take(shot_id, version)
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/video/generate", methods=["POST"])
def generate_video_route(shot_id):
    data = store.get_shot_state(shot_id)
    shot, state = data["shot"], data["state"]
    prompt = pipeline.build_video_prompt(state["working_prompt"])

    image_url = None
    if shot.get("in_else"):
        template_image = store.load_locations().get("else", {}).get("template_image")
        if template_image:
            image_path = ASSETS_DIR / template_image
            if image_path.exists():
                try:
                    image_url = pipeline.upload_local_file(str(image_path))
                except Exception as e:
                    flash(f"Could not upload Else reference image, generating without it: {e}")

    try:
        video_url = pipeline.generate_video(prompt, image_url=image_url)
        out_dir = _shot_output_dir(shot_id, "video")
        version = len(state["video_takes"]) + 1
        out_path = out_dir / f"v{version}.mp4"
        pipeline.download_to_file(video_url, str(out_path))
    except Exception as e:
        flash(f"Video generation failed: {e}")
        return redirect(url_for("shot_detail", shot_id=shot_id))

    store.add_video_take(shot_id, _relative_to_output(out_path), prompt)
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/video/accept/<int:version>", methods=["POST"])
def accept_video(shot_id, version):
    store.accept_video_take(shot_id, version)
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/video/delete/<int:version>", methods=["POST"])
def delete_video_take(shot_id, version):
    store.delete_video_take(shot_id, version)
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/lipsync/generate", methods=["POST"])
def generate_lipsync_route(shot_id):
    data = store.get_shot_state(shot_id)
    shot, state = data["shot"], data["state"]

    if len(shot["dialogue"]) != 1:
        flash("Lipsync only runs on shots with exactly one dialogue line.")
        return redirect(url_for("shot_detail", shot_id=shot_id))
    if not state["accepted_voice"] or not state["accepted_video"]:
        flash("Accept a voice take and a video take before running lipsync.")
        return redirect(url_for("shot_detail", shot_id=shot_id))

    voice_take = next(t for t in state["voice_takes"] if t["version"] == state["accepted_voice"])
    video_take = next(t for t in state["video_takes"] if t["version"] == state["accepted_video"])

    try:
        audio_url = pipeline.upload_local_file(str(OUTPUT_DIR / voice_take["path"]))
        video_url = pipeline.upload_local_file(str(OUTPUT_DIR / video_take["path"]))
        result_url = pipeline.lipsync(video_url, audio_url)
        out_dir = _shot_output_dir(shot_id, "lipsync")
        out_path = out_dir / "final.mp4"
        pipeline.download_to_file(result_url, str(out_path))
    except Exception as e:
        flash(f"Lipsync failed: {e}")
        return redirect(url_for("shot_detail", shot_id=shot_id))

    store.set_lipsync_output(shot_id, _relative_to_output(out_path))
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/shot/<shot_id>/lock", methods=["POST"])
def lock(shot_id):
    data = store.get_shot_state(shot_id)
    shot, state = data["shot"], data["state"]
    if not state["accepted_video"]:
        flash("Accept a video take before locking.")
        return redirect(url_for("shot_detail", shot_id=shot_id))
    if shot["dialogue"] and not state["accepted_voice"]:
        flash("Accept a voice take before locking.")
        return redirect(url_for("shot_detail", shot_id=shot_id))
    store.lock_shot(shot_id)
    return redirect(url_for("shot_detail", shot_id=shot_id))


@app.route("/media/<path:filepath>")
def media(filepath):
    return send_from_directory(OUTPUT_DIR, filepath)


@app.route("/assets/<path:filepath>")
def assets(filepath):
    return send_from_directory(ASSETS_DIR, filepath)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
