"""
Config/state I/O. config/*.json is hand-curated and never rewritten by this
module. state/shots_state.json is the only file that gets mutated, and it
references shots by id rather than copying their content.
"""
import json

from config.settings import (
    CHARACTERS_FILE,
    LOCATIONS_FILE,
    NEVER_HAPPENS_FILE,
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
