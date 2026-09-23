from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
ASSETS_DIR = BASE_DIR / "assets"

SHOTS_FILE = CONFIG_DIR / "shots.json"
CHARACTERS_FILE = CONFIG_DIR / "characters.json"
NEVER_HAPPENS_FILE = CONFIG_DIR / "never_happens.json"
LOCATIONS_FILE = CONFIG_DIR / "locations.json"
PRONUNCIATION_FILE = CONFIG_DIR / "pronunciation.json"
STATE_FILE = STATE_DIR / "shots_state.json"

ART_STYLE_BLOCK = (
    "PS2-era 3D game rendering, low-poly character models, flat shading, "
    "slight texture aliasing, muted early-2000s color palette, "
    "GTA San Andreas / Vice City style graphics."
)

# Split endpoints, no string manipulation on the slug. Swap these two to
# change video model/quality (e.g. to Happy Horse 1.0) without touching pipeline.py.
VIDEO_MODEL_TEXT_ENDPOINT = "fal-ai/minimax/h3-max-turbo/text-to-video"
VIDEO_MODEL_IMAGE_ENDPOINT = "fal-ai/minimax/h3-max-turbo/image-to-video"
VIDEO_MODEL_RESOLUTION = "768p"

ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"

LIPSYNC_ENDPOINT = "veed/lipsync/v2"
