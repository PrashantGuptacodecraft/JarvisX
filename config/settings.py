import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

WORKSPACE_DIR = Path(os.getenv("JARVIS_WORKSPACE", BASE_DIR / "JarvisWorkspace"))

JARVIS_NAME  = os.getenv("JARVIS_NAME",  "Jarvis")
USER_NAME    = os.getenv("USER_NAME",    "Sir")
WAKE_WORD    = os.getenv("WAKE_WORD",    "hello jarvis").lower()
SAFE_MODE    = os.getenv("SAFE_MODE",    "true").lower() == "true"
VOICE_MODE   = os.getenv("VOICE_MODE",   "wake").lower().strip()
VOICE_ALWAYS_ON = VOICE_MODE in {"always", "always_on", "continuous", "handsfree", "hands-free"}
VOICE_WAKE_WORDS = [
    phrase.strip().lower()
    for phrase in os.getenv(
        "VOICE_WAKE_WORDS",
        f"{WAKE_WORD},jarvis,hey jarvis,ok jarvis",
    ).split(",")
    if phrase.strip()
]
VOICE_CONVERSATION_TIMEOUT = int(os.getenv("VOICE_CONVERSATION_TIMEOUT", "20"))
VOICE_WAKE_TIMEOUT = int(os.getenv("VOICE_WAKE_TIMEOUT", "3"))
VOICE_COMMAND_TIMEOUT = int(os.getenv("VOICE_COMMAND_TIMEOUT", "6"))
VOICE_PHRASE_TIME_LIMIT = int(os.getenv("VOICE_PHRASE_TIME_LIMIT", "25"))
VOICE_IDLE_PHRASE_TIME_LIMIT = int(os.getenv("VOICE_IDLE_PHRASE_TIME_LIMIT", "6"))
VOICE_RETRY_SECONDS = int(os.getenv("VOICE_RETRY_SECONDS", "15"))
VOICE_ENERGY_THRESHOLD = int(os.getenv("VOICE_ENERGY_THRESHOLD", "300"))
VOICE_DYNAMIC_ENERGY = os.getenv("VOICE_DYNAMIC_ENERGY", "true").lower() == "true"
VOICE_PAUSE_THRESHOLD = float(os.getenv("VOICE_PAUSE_THRESHOLD", "0.8"))
VOICE_AMBIENT_SECONDS = float(os.getenv("VOICE_AMBIENT_SECONDS", "0.8"))

AI_PROVIDER  = os.getenv("AI_PROVIDER",  "gemini")
GEMINI_KEY   = os.getenv("GEMINI_API_KEY",  "")
OPENAI_KEY   = os.getenv("OPENAI_API_KEY",  "")
GROQ_KEY     = os.getenv("GROQ_API_KEY",    "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GROQ_MODEL   = os.getenv("GROQ_MODEL",   "llama3-70b-8192")

ELEVENLABS_KEY      = os.getenv("ELEVENLABS_API_KEY",  "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_VOICE_NAME = os.getenv("ELEVENLABS_VOICE_NAME", "").strip()
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip()
ELEVENLABS_STABILITY = float(os.getenv("ELEVENLABS_STABILITY", "0.42"))
ELEVENLABS_SIMILARITY_BOOST = float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.88"))
ELEVENLABS_STYLE = float(os.getenv("ELEVENLABS_STYLE", "0.22"))
ELEVENLABS_SPEAKER_BOOST = os.getenv("ELEVENLABS_SPEAKER_BOOST", "true").lower() == "true"
TTS_ENGINE          = os.getenv("TTS_ENGINE", "auto").lower().strip()
VOICE_PROFILE       = os.getenv("VOICE_PROFILE", "cute_girl").lower().strip()
EDGE_VOICE          = os.getenv("EDGE_VOICE", "").strip()
TTS_RATE            = os.getenv("TTS_RATE", "-4%").strip()
TTS_PITCH           = os.getenv("TTS_PITCH", "+4Hz").strip()
TTS_VOLUME          = os.getenv("TTS_VOLUME", "+0%").strip()

LOGS_DIR = BASE_DIR / "logs"
DB_PATH  = BASE_DIR / "jarvis_memory.db"
LOGS_DIR.mkdir(exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

def get_active_provider() -> str:
    pref = AI_PROVIDER.lower()
    mapping = [("gemini", GEMINI_KEY), ("openai", OPENAI_KEY), ("groq", GROQ_KEY)]
    for name, key in mapping:
        if pref == name and key:
            return name
    for name, key in mapping:
        if key:
            return name
    return "none"
