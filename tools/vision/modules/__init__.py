"""
tools/vision/modules/__init__.py
Module registry — auto-loads enabled modules from config/features.json.
"""
from __future__ import annotations
import json, os, logging
from typing import Optional

log = logging.getLogger("modules")

_FEATURES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))),
    "config", "features.json"
)


def load_features() -> dict:
    try:
        with open(_FEATURES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


class ModuleManager:
    """
    Loads and runs all enabled feature modules.
    Each module's update(frame, hand_data, gesture_result) is called every frame.
    """

    def __init__(self) -> None:
        self._modules: list = []
        self._vgf = None   # voice+gesture fusion ref (special: returns fused command)
        self._reload()

    def _reload(self) -> None:
        flags = load_features()
        self._modules.clear()
        self._vgf = None

        if flags.get("air_drawing"):
            try:
                from tools.vision.modules.air_drawing import AirDrawing
                self._modules.append(AirDrawing())
                log.info("Module: air_drawing ENABLED")
            except Exception as e:
                log.warning("air_drawing load failed: %s", e)

        if flags.get("gesture_heatmap"):
            try:
                from tools.vision.modules.gesture_heatmap import GestureHeatmap
                self._modules.append(GestureHeatmap())
                log.info("Module: gesture_heatmap ENABLED")
            except Exception as e:
                log.warning("gesture_heatmap load failed: %s", e)

        if flags.get("ar_overlay"):
            try:
                from tools.vision.modules.ar_overlay import AROverlay
                self._modules.append(AROverlay())
                log.info("Module: ar_overlay ENABLED")
            except Exception as e:
                log.warning("ar_overlay load failed: %s", e)

        if flags.get("voice_gesture_fusion"):
            try:
                from tools.vision.modules.voice_gesture_fusion import VoiceGestureFusion
                self._vgf = VoiceGestureFusion()
                self._modules.append(self._vgf)
                log.info("Module: voice_gesture_fusion ENABLED")
            except Exception as e:
                log.warning("voice_gesture_fusion load failed: %s", e)

    def update(self, frame, hand_data: dict, gesture_result: dict) -> tuple:
        """
        Run all enabled modules. Returns (frame, fused_command|None).
        frame may be annotated in-place by each module.
        """
        fused_cmd = None
        for mod in self._modules:
            try:
                result = mod.update(frame, hand_data, gesture_result)
                if result is not None and isinstance(result, str):
                    fused_cmd = result
            except Exception as e:
                log.debug("Module %s error: %s", mod.__class__.__name__, e)
        return frame, fused_cmd

    def reload(self) -> None:
        """Hot-reload feature flags at runtime."""
        self._reload()
