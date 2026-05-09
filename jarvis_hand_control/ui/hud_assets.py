"""
ui/hud_assets.py
Visual constants for hud_renderer.py and ar_effects.py.
No classes. No functions. Pure constants only.
"""
import cv2

# ── Colors (BGR) ──────────────────────────────────────────────────────────────
COLOR_CYAN    = (255, 255,   0)
COLOR_GREEN   = (  0, 255, 100)
COLOR_RED     = (  0,  60, 255)
COLOR_ORANGE  = (  0, 165, 255)
COLOR_WHITE   = (255, 255, 255)
COLOR_DARK_BG = ( 20,  20,  20)
COLOR_YELLOW  = (  0, 220, 255)
COLOR_PURPLE  = (255,  50, 150)
COLOR_GRAY    = (120, 120, 120)
COLOR_TEAL    = (200, 200,   0)
COLOR_BLACK   = (  0,   0,   0)
COLOR_BLUE    = (255,  80,  20)
COLOR_LIME    = (  0, 255,   0)

# Gesture-specific badge colors (BGR)
GESTURE_COLORS: dict[str, tuple] = {
    "cursor_move":   COLOR_CYAN,
    "left_click":    COLOR_GREEN,
    "right_click":   COLOR_ORANGE,
    "double_click":  COLOR_YELLOW,
    "freeze_cursor": COLOR_TEAL,
    "scroll_up":     (100, 255, 100),
    "scroll_down":   (100, 100, 255),
    "swipe_left":    COLOR_PURPLE,
    "swipe_right":   COLOR_PURPLE,
    "swipe_up":      COLOR_YELLOW,
    "swipe_down":    COLOR_YELLOW,
    "thumbs_up":     COLOR_GREEN,
    "thumbs_down":   COLOR_RED,
    "ok_sign":       COLOR_LIME,
    "peace_sign":    COLOR_CYAN,
    "rock_sign":     COLOR_ORANGE,
    "fist":          COLOR_RED,
    "drawing_mode":  COLOR_TEAL,
    "none":          COLOR_GRAY,
}

# ── Fonts ─────────────────────────────────────────────────────────────────────
FONT               = cv2.FONT_HERSHEY_SIMPLEX
FONT_MONO          = cv2.FONT_HERSHEY_PLAIN
FONT_SCALE_LARGE   = 1.20
FONT_SCALE_MEDIUM  = 0.75
FONT_SCALE_SMALL   = 0.55
FONT_SCALE_TINY    = 0.40
FONT_THICKNESS     = 2
FONT_THICKNESS_THIN= 1

# ── Animation timing ──────────────────────────────────────────────────────────
PULSE_DURATION_FRAMES  = 12
SCAN_LINE_SPEED        = 4    # pixels per frame
CIRCUIT_SCROLL_SPEED   = 1    # pixels per frame
FLASH_DURATION_FRAMES  = 6
WAVEFORM_BARS          = 32
WAVEFORM_MAX_HEIGHT    = 60   # pixels
PARTICLE_TTL_FRAMES    = 18
ENTRY_RING_FRAMES      = 9    # frames for entry animation ring

# ── Layout ────────────────────────────────────────────────────────────────────
CORNER_BRACKET_SIZE      = 30
CORNER_BRACKET_THICKNESS = 2
HISTORY_MAX_ITEMS        = 5
HISTORY_ITEM_HEIGHT      = 22
SIDEBAR_WIDTH            = 220
BADGE_HEIGHT             = 36
BADGE_PADDING            = 10
HUD_MARGIN               = 12

# Skeleton landmark connections (MediaPipe hand topology)
HAND_CONNECTIONS: list[tuple[int, int]] = [
    (0,1),(1,2),(2,3),(3,4),            # thumb
    (0,5),(5,6),(6,7),(7,8),            # index
    (0,9),(9,10),(10,11),(11,12),       # middle
    (0,13),(13,14),(14,15),(15,16),     # ring
    (0,17),(17,18),(18,19),(19,20),     # pinky
    (5,9),(9,13),(13,17),(5,17),        # palm
]

FINGERTIP_IDS = [4, 8, 12, 16, 20]

# Confidence bar thresholds
CONF_HIGH   = 0.80
CONF_MEDIUM = 0.60
CONF_LOW    = 0.40
