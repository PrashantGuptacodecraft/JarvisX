"""
config/settings.py
Central configuration for JARVIS — voice assistant + gesture control system.
All tuneable constants live here — edit once, apply everywhere.
Reads .env via python-dotenv if available, falls back to os.getenv.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import os
from pathlib import Path

# ── Load .env file ────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:
    pass  # dotenv optional — values already set in environment

# ── Top-level constants imported by main.py ───────────────────────────────────

# JARVIS identity
JARVIS_NAME: str = os.getenv("JARVIS_NAME", "JARVIS")
USER_NAME:   str = os.getenv("USER_NAME",   "Sir")

# Wake word
WAKE_WORD:   str = os.getenv("WAKE_WORD",   "hello jarvis")

# Voice mode flags
_voice_mode       = os.getenv("VOICE_MODE", "wake").lower()
VOICE_ALWAYS_ON:  bool = _voice_mode == "always"

# Operator / safe mode
_safe_mode        = os.getenv("SAFE_MODE", "false").lower()
OPERATOR_MODE:    bool = _safe_mode != "true"   # True = operator, False = safe

# Knowledge directory (for memory sync)
KNOWLEDGE_DIR: Path = Path(os.getenv(
    "KNOWLEDGE_DIR",
    str(Path(__file__).resolve().parent.parent / "data" / "knowledge")
))

AI_PROVIDER:  str = os.getenv("AI_PROVIDER",  "gemini")

GEMINI_KEY:   str = os.getenv("GEMINI_API_KEY",  "")
OPENAI_KEY:   str = os.getenv("OPENAI_API_KEY",  "")
GROQ_KEY:     str = os.getenv("GROQ_API_KEY",    "")
XAI_KEY:      str = os.getenv("XAI_API_KEY",     "")

GEMINI_MODEL: str = os.getenv("GEMINI_MODEL",  "gemini-2.0-flash")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL",  "gpt-4o-mini")
GROQ_MODEL:   str = os.getenv("GROQ_MODEL",    "llama-3.3-70b-versatile")
XAI_MODEL:    str = os.getenv("XAI_MODEL",     "grok-beta")
XAI_BASE_URL: str = os.getenv("XAI_BASE_URL",  "https://api.x.ai/v1")

# ── Voice constants ───────────────────────────────────────────────────────────
VOICE_RESPONSE_MAX_TOKENS: int = int(os.getenv("VOICE_RESPONSE_MAX_TOKENS", "120"))
VOICE_MEMORY_CONTEXT_ITEMS: int = int(os.getenv("VOICE_MEMORY_CONTEXT_ITEMS", "3"))
VOICE_HISTORY_ITEMS: int = int(os.getenv("VOICE_HISTORY_ITEMS", "2"))
VOICE_ENERGY_THRESHOLD: int = int(os.getenv("VOICE_ENERGY_THRESHOLD", "300"))
VOICE_PAUSE_THRESHOLD: float = float(os.getenv("VOICE_PAUSE_THRESHOLD", "0.55"))
VOICE_AMBIENT_SECONDS: float = float(os.getenv("VOICE_AMBIENT_SECONDS", "0.35"))
VOICE_COMMAND_TIMEOUT: int = int(os.getenv("VOICE_COMMAND_TIMEOUT", "4"))
VOICE_PHRASE_TIME_LIMIT: int = int(os.getenv("VOICE_PHRASE_TIME_LIMIT", "8"))
VOICE_CONVERSATION_TIMEOUT: int = int(os.getenv("VOICE_CONVERSATION_TIMEOUT", "12"))

# ── Safe mode / Workspace ─────────────────────────────────────────────────────
SAFE_MODE: bool = os.getenv("SAFE_MODE", "false").lower() == "true"

WORKSPACE_DIR: Path = Path(os.getenv(
    "WORKSPACE_DIR",
    str(Path(__file__).resolve().parent.parent / "workspace")
))

# ── Database paths (Path objects — memory/manager.py calls .parent.mkdir()) ───
_DB_PATH_RAW: str = os.getenv(
    "DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "jarvis.db")
)
DB_PATH: Path = Path(_DB_PATH_RAW)

_FALLBACK_DB_PATH_RAW: str = os.getenv(
    "FALLBACK_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "jarvis_backup.db")
)
FALLBACK_DB_PATH: Path = Path(_FALLBACK_DB_PATH_RAW)

# ── TTS / Speaker constants (voice/speaker.py) ────────────────────────────────
TTS_ENGINE:   str   = os.getenv("TTS_ENGINE",   "auto")
VOICE_PROFILE: str  = os.getenv("VOICE_PROFILE", "human_girl")
EDGE_VOICE:   str   = os.getenv("EDGE_VOICE",   "en-US-AriaNeural")
TTS_RATE:     str   = os.getenv("TTS_RATE",     "+0%")
TTS_PITCH:    str   = os.getenv("TTS_PITCH",    "+0Hz")
TTS_VOLUME:   str   = os.getenv("TTS_VOLUME",   "+0%")

# ElevenLabs
ELEVENLABS_KEY:              str   = os.getenv("ELEVENLABS_API_KEY",       "")
ELEVENLABS_VOICE_ID:         str   = os.getenv("ELEVENLABS_VOICE_ID",      "")
ELEVENLABS_VOICE_NAME:       str   = os.getenv("ELEVENLABS_VOICE_NAME",    "")
ELEVENLABS_MODEL_ID:         str   = os.getenv("ELEVENLABS_MODEL_ID",      "eleven_multilingual_v2")
ELEVENLABS_STABILITY:        float = float(os.getenv("ELEVENLABS_STABILITY",        "0.42"))
ELEVENLABS_SIMILARITY_BOOST: float = float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.88"))
ELEVENLABS_STYLE:            float = float(os.getenv("ELEVENLABS_STYLE",            "0.22"))
ELEVENLABS_SPEAKER_BOOST:    bool  = os.getenv("ELEVENLABS_SPEAKER_BOOST", "true").lower() == "true"

# ── Voice listener constants (voice/listener.py) ──────────────────────────────
VOICE_WAKE_WORDS: str   = os.getenv("VOICE_WAKE_WORDS",
                                     "hello jarvis,jarvis,hey jarvis,ok jarvis")
VOICE_DYNAMIC_ENERGY: bool = os.getenv("VOICE_DYNAMIC_ENERGY", "true").lower() == "true"
VOICE_WAKE_TIMEOUT:   int  = int(os.getenv("VOICE_WAKE_TIMEOUT",       "2"))
VOICE_IDLE_PHRASE_TIME_LIMIT: int = int(os.getenv("VOICE_IDLE_PHRASE_TIME_LIMIT", "3"))
VOICE_SILENCE_SECONDS: float = float(os.getenv("VOICE_SILENCE_SECONDS", "0.55"))
VOICE_RETRY_SECONDS:   int  = int(os.getenv("VOICE_RETRY_SECONDS",   "15"))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@dataclass
class CameraSettings:
    index: int   = 0
    width: int   = 640
    height: int  = 480
    fps: int     = 30
    backend: str = "DSHOW"   # "DSHOW" | "MSMF" | "AUTO"

@dataclass
class DetectionSettings:
    model_path: str    = os.path.join(BASE_DIR, "models", "hand_landmarker.task")
    num_hands: int     = 1
    min_detect: float  = 0.65
    min_presence: float= 0.55
    min_track: float   = 0.55

@dataclass
class CursorSettings:
    smooth_alpha: float  = 0.30    # EMA weight  (0=frozen, 1=raw)
    dead_zone_px: int    = 6       # ignore movements smaller than this
    max_jump_px: int     = 130     # cap single-frame jump
    map_x0: float        = 0.10   # left crop margin (normalized)
    map_x1: float        = 0.90   # right crop margin
    map_y0: float        = 0.10   # top crop margin
    map_y1: float        = 0.85   # bottom crop margin
    accel_slow_mult: float = 0.50  # multiplier at slow velocity
    accel_fast_mult: float = 2.20  # multiplier at fast velocity
    accel_slow_vel: float  = 0.04  # normalized velocity threshold
    accel_fast_vel: float  = 0.15  # normalized velocity threshold
    edge_dist_px: int    = 40      # edge magnetism zone
    edge_mult: float     = 0.30    # speed reduction near edge

@dataclass
class GestureSettings:
    pinch_thresh: float  = 0.075  # thumb-index pinch click distance
    confirm_frames: int  = 4      # frames needed to confirm gesture
    click_frames: int    = 2      # faster confirm for click
    vol_frames: int      = 7      # slower confirm for volume
    scroll_interval: float = 0.08 # seconds between continuous scroll ticks
    scroll_amount: int   = 4      # scroll units per tick
    click_cooldown: float= 0.55   # seconds between clicks
    pre_click_freeze: float = 0.10
    post_click_freeze: float= 0.22
    vote_window: int     = 7      # majority-vote buffer size
    vote_threshold: int  = 5      # required votes

@dataclass
class HUDSettings:
    show: bool           = True
    skeleton_color: tuple= (255, 255, 255)
    tip_color: tuple     = (0, 255, 136)
    font_scale: float    = 0.85
    corner_color: tuple  = (0, 200, 255)
    corner_len: int      = 26

@dataclass
class AnalyticsSettings:
    dashboard_port: int  = 5050
    heatmap_decay: float = 0.995
    heatmap_blur: int    = 25
    save_dir: str        = os.path.join(BASE_DIR, "data", "analytics")

@dataclass
class Settings:
    camera:    CameraSettings    = field(default_factory=CameraSettings)
    detection: DetectionSettings = field(default_factory=DetectionSettings)
    cursor:    CursorSettings    = field(default_factory=CursorSettings)
    gesture:   GestureSettings   = field(default_factory=GestureSettings)
    hud:       HUDSettings       = field(default_factory=HUDSettings)
    analytics: AnalyticsSettings = field(default_factory=AnalyticsSettings)

# Global singleton — import this everywhere
cfg = Settings()
