"""
Config/state I/O. config/shots.json is treated as curated data the UI is
allowed to manage directly (title, characters, location, existence), since
those are structural properties with no "takes" or "versions". Generation
iteration (working prompt/dialogue, takes, accepted/locked) lives only in
state/shots_state.json, which references shots by id.
"""
import json
import re

from config.settings import (
    CHARACTERS_FILE,
    LOCATIONS_FILE,
    NEVER_HAPPENS_FILE,
    PRONUNCIATION_FILE,
    SHOTS_FILE,
    STATE_FILE,
)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def load_characters():
    return _read_json(CHARACTERS_FILE)["characters"]


def load_shots():
    return _read_json(SHOTS_FILE)["shots"]


def load_shot(shot_id):
    for shot in load_shots():
        if shot["id"] == shot_id:
            return shot
    return None


def load_never_happens():
    return _read_json(NEVER_HAPPENS_FILE)["never_happens"]


def load_locations():
    return _read_json(LOCATIONS_FILE)


def load_pronunciation():
    if not PRONUNCIATION_FILE.exists():
        return {}
    return _read_json(PRONUNCIATION_FILE)


def apply_pronunciation(text):
    """Rewrites words to their phonetic spelling before TTS (e.g. Else -> Ellse),
    so English-reading models say them the German way. Whole-word, case-sensitive."""
    for word, phonetic in load_pronunciation().items():
        text = re.sub(r"\b" + re.escape(word) + r"\b", phonetic, text)
    return text


def resolve_location(shot):
    location_id = shot.get("location_id") or ("else" if shot.get("in_else") else None)
    if not location_id:
        return None
    return load_locations().get(location_id)


def character_design_blocks(character_ids):
    characters = load_characters()
    blocks = []
    for cid in character_ids:
        design = characters.get(cid, {}).get("design")
        if design:
            blocks.append(design)
    return " ".join(blocks)


def load_state():
    if not STATE_FILE.exists():
        return {}
    return _read_json(STATE_FILE)


def save_state(state):
    _write_json(STATE_FILE, state)


def _blank_shot_state(shot):
    return {
        "working_prompt": shot["visual_prompt"],
        "working_dialogue": [dict(d) for d in shot["dialogue"]],
        "voice_takes": [],
        "video_takes": [],
        "accepted_voice": None,
        "accepted_video": None,
        "lipsync_output": None,
        "locked": False,
    }


def get_shot_state(shot_id):
    """Curated shot merged with its runtime state, initializing state on first access."""
    shot = load_shot(shot_id)
    if shot is None:
        return None
    state = load_state()
    if shot_id not in state:
        state[shot_id] = _blank_shot_state(shot)
        save_state(state)
    return {"shot": shot, "state": state[shot_id]}


def resolve_voice_id(character_id, override=None):
    if override:
        return override
    if not character_id:
        return None
    characters = load_characters()
    char = characters.get(character_id)
    if not char:
        return None
    return char.get("voice_id") or None


def update_working_prompt(shot_id, prompt):
    state = load_state()
    state[shot_id]["working_prompt"] = prompt
    save_state(state)


def update_working_dialogue_line(shot_id, index, line):
    state = load_state()
    state[shot_id]["working_dialogue"][index]["line"] = line
    save_state(state)


def add_voice_take(shot_id, path, text_used, voice_id_used, character):
    state = load_state()
    takes = state[shot_id]["voice_takes"]
    version = len(takes) + 1
    takes.append({
        "version": version,
        "path": path,
        "text_used": text_used,
        "voice_id_used": voice_id_used,
        "character": character,
    })
    save_state(state)
    return version


def accept_voice_take(shot_id, version):
    state = load_state()
    state[shot_id]["accepted_voice"] = version
    save_state(state)


def add_video_take(shot_id, path, prompt_used):
    state = load_state()
    takes = state[shot_id]["video_takes"]
    version = len(takes) + 1
    takes.append({"version": version, "path": path, "prompt_used": prompt_used})
    save_state(state)
    return version


def accept_video_take(shot_id, version):
    state = load_state()
    state[shot_id]["accepted_video"] = version
    save_state(state)


def set_lipsync_output(shot_id, path):
    state = load_state()
    state[shot_id]["lipsync_output"] = path
    save_state(state)


def lock_shot(shot_id):
    state = load_state()
    state[shot_id]["locked"] = True
    save_state(state)


def unlock_shot(shot_id):
    state = load_state()
    state[shot_id]["locked"] = False
    save_state(state)


def save_shots(shots):
    _write_json(SHOTS_FILE, {"shots": shots})


def _slugify(title):
    slug = re.sub(r"[^a-z0-9]+", "_", title.strip().lower()).strip("_")
    return slug or "shot"


def create_shot(title, visual_prompt="", characters=None, in_else=True, style=None):
    shots = load_shots()
    existing_ids = {s["id"] for s in shots}
    base = _slugify(title)
    shot_id = base
    n = 2
    while shot_id in existing_ids:
        shot_id = f"{base}_{n}"
        n += 1
    new_shot = {
        "id": shot_id,
        "title": title,
        "in_else": in_else,
        "characters": characters or [],
        "visual_prompt": visual_prompt,
        "dialogue": [],
    }
    if style:
        new_shot["style"] = style
    shots.append(new_shot)
    save_shots(shots)
    return shot_id


def delete_shot(shot_id):
    shots = [s for s in load_shots() if s["id"] != shot_id]
    save_shots(shots)
    state = load_state()
    if shot_id in state:
        del state[shot_id]
        save_state(state)


def update_shot_title(shot_id, title):
    shots = load_shots()
    for s in shots:
        if s["id"] == shot_id:
            s["title"] = title
            break
    save_shots(shots)


def update_shot_characters(shot_id, characters):
    shots = load_shots()
    for s in shots:
        if s["id"] == shot_id:
            s["characters"] = characters
            break
    save_shots(shots)


def update_shot_in_else(shot_id, in_else):
    shots = load_shots()
    for s in shots:
        if s["id"] == shot_id:
            s["in_else"] = in_else
            break
    save_shots(shots)


def update_shot_style(shot_id, style):
    shots = load_shots()
    for s in shots:
        if s["id"] == shot_id:
            if style:
                s["style"] = style
            else:
                s.pop("style", None)
            break
    save_shots(shots)


def duplicate_shot(shot_id):
    shot = load_shot(shot_id)
    if shot is None:
        return None
    shots = load_shots()
    existing_ids = {s["id"] for s in shots}
    base = _slugify(shot["title"] + " copy")
    new_id = base
    n = 2
    while new_id in existing_ids:
        new_id = f"{base}_{n}"
        n += 1
    new_shot = {
        "id": new_id,
        "title": f"{shot['title']} (copy)",
        "in_else": shot["in_else"],
        "characters": list(shot["characters"]),
        "visual_prompt": shot["visual_prompt"],
        "dialogue": [dict(d) for d in shot["dialogue"]],
    }
    if shot.get("style"):
        new_shot["style"] = shot["style"]
    shots.append(new_shot)
    save_shots(shots)
    return new_id


def move_shot(shot_id, direction):
    shots = load_shots()
    idx = next((i for i, s in enumerate(shots) if s["id"] == shot_id), None)
    if idx is None:
        return
    if direction == "up" and idx > 0:
        shots[idx - 1], shots[idx] = shots[idx], shots[idx - 1]
    elif direction == "down" and idx < len(shots) - 1:
        shots[idx + 1], shots[idx] = shots[idx], shots[idx + 1]
    save_shots(shots)


def add_dialogue_line(shot_id, character, line):
    entry = {"character": character or None, "line": line, "voice_id": None}
    shots = load_shots()
    for s in shots:
        if s["id"] == shot_id:
            s["dialogue"].append(dict(entry))
            break
    save_shots(shots)
    state = load_state()
    if shot_id in state:
        state[shot_id]["working_dialogue"].append(dict(entry))
        save_state(state)


def remove_dialogue_line(shot_id, index):
    shots = load_shots()
    for s in shots:
        if s["id"] == shot_id and 0 <= index < len(s["dialogue"]):
            del s["dialogue"][index]
            break
    save_shots(shots)
    state = load_state()
    if shot_id in state and 0 <= index < len(state[shot_id]["working_dialogue"]):
        del state[shot_id]["working_dialogue"][index]
        save_state(state)


def delete_voice_take(shot_id, version):
    state = load_state()
    s = state[shot_id]
    s["voice_takes"] = [t for t in s["voice_takes"] if t["version"] != version]
    if s["accepted_voice"] == version:
        s["accepted_voice"] = None
    save_state(state)


def delete_video_take(shot_id, version):
    state = load_state()
    s = state[shot_id]
    s["video_takes"] = [t for t in s["video_takes"] if t["version"] != version]
    if s["accepted_video"] == version:
        s["accepted_video"] = None
    save_state(state)
