from shared_core.dev_tools.style_model import CodingStyleModel
import re

class StyleApplication:
    def __init__(self, style_model: CodingStyleModel):
        self.style = style_model

    def validate_code(self, code: str) -> bool:
        """
        Validates if the provided code matches the style model.
        Returns True if it matches, False otherwise.
        """
        lines = code.splitlines()
        for line in lines:
            if len(line) > self.style.max_line_length:
                return False
                
            # Check indentation style
            if line.lstrip() != "":
                indent = line[:len(line) - len(line.lstrip())]
                if self.style.indent_style == "space":
                    if "\t" in indent:
                        return False
                    if len(indent) % self.style.indent_size != 0:
                        return False
                elif self.style.indent_style == "tab":
                    if " " in indent:
                        return False

        return True
