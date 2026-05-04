"""tools/vision/controller.py — OCR and screen analysis."""
from config.settings import USER_NAME
from config.logger import get_logger
log = get_logger("vision")


class VisionController:
    def read_screen_text(self) -> str:
        try:
            import pyautogui
            img = pyautogui.screenshot()
            return self._ocr(img)
        except Exception as e:
            return f"Screen read failed: {e}"

    def _ocr(self, img) -> str:
        try:
            import pytesseract
            text = pytesseract.image_to_string(img)
            if text.strip():
                return f"Screen text:\n{text.strip()[:800]}"
        except Exception:
            pass
        try:
            import easyocr, numpy as np
            reader = easyocr.Reader(["en"], verbose=False)
            result = reader.readtext(np.array(img))
            text = " ".join(r[1] for r in result)
            if text.strip():
                return f"Screen text:\n{text.strip()[:800]}"
        except Exception:
            pass
        return f"OCR unavailable. Install pytesseract or easyocr, {USER_NAME}."
