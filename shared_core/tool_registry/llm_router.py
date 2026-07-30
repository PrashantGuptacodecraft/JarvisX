from typing import Protocol, List

class LLMRouter(Protocol):
    def generate_text(self, prompt: str) -> str:
        """Synchronously generate text for a given prompt."""
        ...
