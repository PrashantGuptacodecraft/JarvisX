"""
core/fusion_commands.py
FUSION_COMMAND_MAP — single source of truth for all voice+gesture fusion mappings.
Key format: "voice_phrase+gesture_name"
"""
from __future__ import annotations

FUSION_COMMAND_MAP: dict[str, dict] = {
    "open+cursor_move": {
        "action": "open_file_under_cursor",
        "description": "Open the file or link currently under the cursor",
        "min_fusion_score": 0.70,
        "feedback": "Opening item under cursor",
    },
    "close+fist": {
        "action": "close_active_window",
        "description": "Close the currently active window",
        "min_fusion_score": 0.72,
        "feedback": "Closing window",
    },
    "search+peace_sign": {
        "action": "open_browser_search",
        "description": "Open a new browser tab and focus the address bar",
        "min_fusion_score": 0.68,
        "feedback": "Opening browser search",
    },
    "save+ok_sign": {
        "action": "ctrl_s",
        "description": "Save the current document with Ctrl+S",
        "min_fusion_score": 0.75,
        "feedback": "Saving document",
    },
    "bigger+swipe_up": {
        "action": "increase_window_size",
        "description": "Maximise or increase the active window size",
        "min_fusion_score": 0.70,
        "feedback": "Maximising window",
    },
    "undo+thumbs_down": {
        "action": "ctrl_z",
        "description": "Undo the last action with Ctrl+Z",
        "min_fusion_score": 0.72,
        "feedback": "Undoing last action",
    },
    "screenshot+peace_sign": {
        "action": "take_screenshot",
        "description": "Capture and save a screenshot of the full screen",
        "min_fusion_score": 0.80,
        "feedback": "Screenshot captured",
    },
    "jarvis+rock_sign": {
        "action": "open_ai_chat",
        "description": "Open the JARVIS AI chat interface",
        "min_fusion_score": 0.85,
        "feedback": "Opening JARVIS AI chat",
    },
    "play+thumbs_up": {
        "action": "media_play_pause",
        "description": "Toggle media play or pause",
        "min_fusion_score": 0.68,
        "feedback": "Play/pause toggled",
    },
    "stop+fist": {
        "action": "media_stop",
        "description": "Stop media playback",
        "min_fusion_score": 0.72,
        "feedback": "Media stopped",
    },
    "next+swipe_right": {
        "action": "media_next_track",
        "description": "Skip to the next media track",
        "min_fusion_score": 0.68,
        "feedback": "Next track",
    },
    "volume+thumbs_up": {
        "action": "volume_up",
        "description": "Increase system volume",
        "min_fusion_score": 0.65,
        "feedback": "Volume up",
    },
    "volume+thumbs_down": {
        "action": "volume_down",
        "description": "Decrease system volume",
        "min_fusion_score": 0.65,
        "feedback": "Volume down",
    },
    "new+peace_sign": {
        "action": "new_tab",
        "description": "Open a new browser tab with Ctrl+T",
        "min_fusion_score": 0.70,
        "feedback": "New tab opened",
    },
    "back+swipe_left": {
        "action": "browser_back",
        "description": "Navigate back in the browser with Alt+Left",
        "min_fusion_score": 0.68,
        "feedback": "Going back",
    },
    "zoom+ok_sign": {
        "action": "zoom_in",
        "description": "Zoom in with Ctrl+Plus",
        "min_fusion_score": 0.72,
        "feedback": "Zooming in",
    },
    "copy+peace_sign": {
        "action": "ctrl_c",
        "description": "Copy selected content with Ctrl+C",
        "min_fusion_score": 0.75,
        "feedback": "Copied to clipboard",
    },
    "paste+ok_sign": {
        "action": "ctrl_v",
        "description": "Paste clipboard content with Ctrl+V",
        "min_fusion_score": 0.75,
        "feedback": "Pasted from clipboard",
    },
    "select+rock_sign": {
        "action": "ctrl_a",
        "description": "Select all content with Ctrl+A",
        "min_fusion_score": 0.78,
        "feedback": "All selected",
    },
    "delete+thumbs_down": {
        "action": "delete_key",
        "description": "Press the Delete key to remove selected content",
        "min_fusion_score": 0.80,
        "feedback": "Deleted",
    },
}
