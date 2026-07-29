from shared_core.dev_tools.style_model import CodingStyleModel
from .event_models import DevEventEnvelope
from shared_core.event_bus.topics import PERCEPTION_DEV_STYLE_VALIDATION_COMPLETED
from shared_core.event_bus.bus import EventBus
import re
import time
import datetime
from typing import Optional

class StyleApplication:
    def __init__(self, style_model: CodingStyleModel, event_bus: Optional[EventBus] = None):
        self.style = style_model
        self.event_bus = event_bus

    def validate_code(self, code: str) -> bool:
        """
        Validates if the provided code matches the style model.
        Returns True if it matches, False otherwise.
        """
        start_time = time.time()
        is_valid = True
        
        lines = code.splitlines()
        for line in lines:
            if len(line) > self.style.max_line_length:
                is_valid = False
                break
                
            # Check indentation style
            if line.lstrip() != "":
                indent = line[:len(line) - len(line.lstrip())]
                if self.style.indent_style == "space":
                    if "\t" in indent:
                        is_valid = False
                        break
                    if len(indent) % self.style.indent_size != 0:
                        is_valid = False
                        break
                elif self.style.indent_style == "tab":
                    if " " in indent:
                        is_valid = False
                        break

        if self.event_bus:
            duration_ms = (time.time() - start_time) * 1000
            env = DevEventEnvelope(
                schema_version=1,
                event_type=PERCEPTION_DEV_STYLE_VALIDATION_COMPLETED,
                event_id=f"evt_{int(time.time()*1000)}",
                operation="style_validation",
                request_id=None,
                repository_id=None,
                occurred_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                duration_ms=duration_ms,
                status="success" if is_valid else "failed",
                summary={"is_valid": is_valid}
            )
            self.event_bus.publish(PERCEPTION_DEV_STYLE_VALIDATION_COMPLETED, env.to_dict())

        return is_valid
