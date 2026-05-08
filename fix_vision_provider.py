"""fix_vision_provider.py — force Gemini for vision even when primary provider is Groq"""
import os
BASE = os.path.dirname(__file__)
path = os.path.join(BASE, "brain", "ai_client.py")
c = open(path, "r", encoding="utf-8").read()

# Find the start of chat_with_image and replace the whole provider check block
OLD = '''        # ── Gemini Vision ────────────────────────────────────────────────
        if self.provider == "gemini" and self.client:
            try:
                from google.genai import types
                with open(image_path, "rb") as f:
                    image_bytes = f.read()'''

NEW = '''        # ── Gemini Vision (always try first, even if primary provider is Groq/etc.) ──
        # Build dedicated Gemini client for vision using GEMINI_KEY directly
        _vis_client = None
        if GEMINI_KEY:
            try:
                from google import genai as _gv
                _vis_client = _gv.Client(api_key=GEMINI_KEY)
            except Exception as _ge:
                log.warning("Could not init Gemini vision client: %s", _ge)

        if _vis_client:
            try:
                from google.genai import types
                with open(image_path, "rb") as f:
                    image_bytes = f.read()'''

if OLD in c:
    c = c.replace(OLD, NEW, 1)
    # Replace self.client.models.generate_content inside vision block with _vis_client
    c = c.replace(
        '                        resp = self.client.models.generate_content(model=model_name, contents=contents)',
        '                        resp = _vis_client.models.generate_content(model=model_name, contents=contents)',
        1
    )
    open(path, "w", encoding="utf-8").write(c)
    print("Vision fix applied: Gemini always used for images")
else:
    # Try alternate search
    idx = c.find("if self.provider == \"gemini\" and self.client:\n            try:\n                from google.genai import types")
    if idx > 0:
        # Find enclosing block and patch the condition
        c = c.replace(
            'if self.provider == "gemini" and self.client:\n            try:\n                from google.genai import types',
            '''# Always try Gemini for vision
        _vis_client = None
        if GEMINI_KEY:
            try:
                from google import genai as _gv
                _vis_client = _gv.Client(api_key=GEMINI_KEY)
            except Exception: pass
        if _vis_client:
            try:
                from google.genai import types''',
            1
        )
        c = c.replace(
            'resp = self.client.models.generate_content(model=model_name, contents=contents)',
            'resp = _vis_client.models.generate_content(model=model_name, contents=contents)',
            1
        )
        open(path, "w", encoding="utf-8").write(c)
        print("Vision fix applied (alternate path)")
    else:
        print("ERROR: Could not find vision block - showing context:")
        idx2 = c.find("chat_with_image")
        print(c[idx2:idx2+600])
