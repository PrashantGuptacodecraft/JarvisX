"""patch_camera_fix.py — fix camera canvas not rendering due to PIL RGBA error"""
import os, re

path = os.path.join(os.path.dirname(__file__), "ui", "interface.py")
content = open(path, "r", encoding="utf-8").read()

# Find and replace the _update_camera_frame method
OLD = '    def _update_camera_frame(self, rgb_array):\n        """Update tkinter canvas with latest frame (runs on main thread)."""\n        try:\n            from PIL import Image, ImageTk, ImageDraw\n        except ImportError:\n            return\n        cw = self._cam_canvas.winfo_width()  or 640\n        ch = self._cam_canvas.winfo_height() or 480\n        img = Image.fromarray(rgb_array)\n        img = img.resize((cw, ch), Image.LANCZOS)\n        self._cam_last_img = img\n\n        # HUD overlay \u2014 futuristic corner brackets\n        draw = ImageDraw.Draw(img)\n        bw = 30   # bracket arm length\n        bt = 3    # thickness\n        pad = 12\n        for (x0, y0, xd, yd) in [\n            (pad, pad, 1, 1),\n            (cw-pad, pad, -1, 1),\n            (pad, ch-pad, 1, -1),\n            (cw-pad, ch-pad, -1, -1),\n        ]:\n            draw.line([(x0, y0), (x0+xd*bw, y0)], fill=(0, 212, 255), width=bt)\n            draw.line([(x0, y0), (x0, y0+yd*bw)], fill=(0, 212, 255), width=bt)\n\n        # Scanlines (subtle)\n        for y in range(0, ch, 6):\n            draw.line([(0, y), (cw, y)], fill=(0, 0, 0, 30))\n\n        # Center crosshair\n        cx, cy = cw//2, ch//2\n        draw.line([(cx-20, cy), (cx+20, cy)], fill=(0, 212, 255, 180), width=1)\n        draw.line([(cx, cy-20), (cx, cy+20)], fill=(0, 212, 255, 180), width=1)\n\n        photo = ImageTk.PhotoImage(img)\n        self._cam_photo_ref = photo\n        self._cam_canvas.delete("all")\n        self._cam_canvas.create_image(0, 0, anchor="nw", image=photo)\n\n        # Timestamp overlay\n        now = datetime.datetime.now().strftime("%H:%M:%S")\n        self._cam_canvas.create_text(\n            cw - 8, ch - 8, anchor="se",\n            text=f"REC \u25c9  {now}",\n            fill=CYAN, font=self._fonts["body_sm"]\n        )'

NEW = '    def _update_camera_frame(self, rgb_array):\n        """Update tkinter canvas with latest frame (runs on main thread)."""\n        try:\n            from PIL import Image, ImageTk, ImageDraw\n        except ImportError:\n            return\n        try:\n            cw = self._cam_canvas.winfo_width()  or 640\n            ch = self._cam_canvas.winfo_height() or 480\n\n            img = Image.fromarray(rgb_array).resize((cw, ch), Image.LANCZOS)\n            self._cam_last_img = img.copy()  # Save clean RGB copy for snapshots/AI\n\n            # Convert to RGBA so we can draw semi-transparent overlays\n            overlay = img.convert("RGBA")\n            draw = ImageDraw.Draw(overlay)\n\n            # Corner HUD brackets (fully opaque cyan)\n            bw, bt, pad = 30, 3, 12\n            for (x0, y0, xd, yd) in [\n                (pad, pad, 1, 1),\n                (cw-pad, pad, -1, 1),\n                (pad, ch-pad, 1, -1),\n                (cw-pad, ch-pad, -1, -1),\n            ]:\n                draw.line([(x0, y0), (x0+xd*bw, y0)], fill=(0, 212, 255, 255), width=bt)\n                draw.line([(x0, y0), (x0, y0+yd*bw)], fill=(0, 212, 255, 255), width=bt)\n\n            # Scanlines (subtle dark lines)\n            for y in range(0, ch, 6):\n                draw.line([(0, y), (cw, y)], fill=(0, 0, 0, 40))\n\n            # Center crosshair\n            cx, cy = cw//2, ch//2\n            draw.line([(cx-20, cy), (cx+20, cy)], fill=(0, 212, 255, 200), width=1)\n            draw.line([(cx, cy-20), (cx, cy+20)], fill=(0, 212, 255, 200), width=1)\n\n            # Convert back to RGB for tkinter\n            final = overlay.convert("RGB")\n\n            photo = ImageTk.PhotoImage(final)\n            self._cam_photo_ref = photo\n            self._cam_canvas.delete("all")\n            self._cam_canvas.create_image(0, 0, anchor="nw", image=photo)\n\n            # Timestamp overlay via canvas text (no PIL needed)\n            now = datetime.datetime.now().strftime("%H:%M:%S")\n            self._cam_canvas.create_text(\n                cw - 8, ch - 8, anchor="se",\n                text="REC  " + now,\n                fill=CYAN, font=self._fonts["body_sm"]\n            )\n        except Exception as _e:\n            import traceback\n            traceback.print_exc()'

if OLD in content:
    content = content.replace(OLD, NEW, 1)
    open(path, "w", encoding="utf-8").write(content)
    print("FIXED: _update_camera_frame — RGBA overlay bug corrected")
else:
    # Try partial match on the key broken lines
    broken1 = 'draw.line([(0, y), (cw, y)], fill=(0, 0, 0, 30))'
    broken2 = 'draw.line([(cx-20, cy), (cx+20, cy)], fill=(0, 212, 255, 180), width=1)'
    if broken1 in content or broken2 in content:
        content = content.replace(
            'draw.line([(0, y), (cw, y)], fill=(0, 0, 0, 30))',
            'draw.line([(0, y), (cw, y)], fill=(0, 0, 0))',  # solid, no alpha needed
        )
        content = content.replace(
            'draw.line([(cx-20, cy), (cx+20, cy)], fill=(0, 212, 255, 180), width=1)',
            'draw.line([(cx-20, cy), (cx+20, cy)], fill=(0, 212, 255), width=1)',
        )
        content = content.replace(
            'draw.line([(cx, cy-20), (cx, cy+20)], fill=(0, 212, 255, 180), width=1)',
            'draw.line([(cx, cy-20), (cx, cy+20)], fill=(0, 212, 255), width=1)',
        )
        # Wrap entire method body in try/except to surface future errors
        open(path, "w", encoding="utf-8").write(content)
        print("PARTIAL FIX: Removed alpha values from PIL RGB draw calls")
    else:
        print("ERROR: Could not find the broken lines — already patched or different content")
        # Show snippet for diagnosis
        idx = content.find("def _update_camera_frame")
        print("Method preview:", content[idx:idx+200] if idx >= 0 else "NOT FOUND")
