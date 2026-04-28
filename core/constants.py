"""Application constants and configuration defaults."""

# Gemini API
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"
GEMINI_IMAGE_MAX_SIZE_BYTES = 4 * 1024 * 1024  # 4MB
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_MIN_WAIT = 2
GEMINI_RETRY_MAX_WAIT = 30
# Max image-gen turns (user+model pairs) to send with each generate_image call.
# Beyond this we truncate what we send — the full history is still persisted so
# resuming a project keeps the full chain.
GEMINI_MAX_HISTORY_TURNS = 6

# Kling API
KLING_API_BASE = "https://api.klingai.com"
KLING_MODEL = "kling-v2.6-pro"
KLING_JWT_EXPIRY_SEC = 1800
KLING_JWT_REFRESH_BUFFER_SEC = 60
KLING_POLL_INTERVAL_SEC = 10
KLING_TIMEOUT_SEC = 600
KLING_MAX_RETRIES = 3
KLING_RETRY_MIN_WAIT = 5
KLING_RETRY_MAX_WAIT = 60
KLING_MAX_WORKERS = 1  # Kling Direct's free pack rejects >1 parallel task with code 1303
KLING_DURATIONS = [5.0, 10.0]
KLING_ASPECT_RATIOS = ["16:9", "9:16", "1:1"]

# Scene limits
MAX_SCENES = 50
MAX_SCRIPT_LENGTH = 50000
MAX_GENERATION_ATTEMPTS = 3

# UI
SCENE_GRID_COLUMNS = 3
SUPPORTED_IMAGE_TYPES = ["jpg", "jpeg", "png", "webp"]

# Creative brief
MAX_REFERENCE_IMAGES = 10
DEFAULT_DATA_DIR = "~/.scene_studio/projects"

STYLE_PRESETS = [
    "Anime",
    "Watercolor",
    "Photorealistic",
    "Comic Book",
    "Pixel Art",
    "Oil Painting",
    "3D Render",
    "Flat Illustration",
]
