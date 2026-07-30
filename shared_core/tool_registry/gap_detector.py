from typing import List, Optional, Tuple
from .gap_model import ToolGap, ToolGapKind
from .registry import ToolRegistry
import re

class ToolGapDetector:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def detect_intent_gap(self, intent: str) -> Optional[ToolGap]:
        """
        Detect if an intent string lacks a corresponding registered handler.
        This is a simple heuristic based on keywords in the intent.
        """
        # Very simplistic NLP: extract the first verb/action
        intent = intent.lower().strip()
        words = intent.split()
        if not words:
            return None
        
        # Check against registered tool descriptions and names
        tools = self.registry.list_tools()
        
        # Look for direct keyword match
        for t in tools:
            if words[0] in t.name.lower() or words[0] in t.description.lower():
                return None
                
        # If no match found, raise a gap
        return ToolGap(
            kind=ToolGapKind.UNHANDLED_INTENT,
            description=f"No registered tool handles the intent: '{intent}'",
            suggested_tool_name=f"{words[0]}_tool",
            evidence=[intent]
        )

    def detect_repeated_sequence(self, history: List[str], threshold: int = 3) -> Optional[ToolGap]:
        """
        Detect a repeated sequence of manual operations from history.
        """
        if len(history) < threshold * 2:
            return None
            
        # Look for repeated bigrams or trigrams
        n_grams = {}
        # We look for sequences of length 3 then 2 to favor longer ones
        for seq_len in (3, 2):
            for i in range(len(history) - seq_len + 1):
                seq = tuple(history[i:i+seq_len])
                n_grams[seq] = n_grams.get(seq, 0) + 1
                
            for seq, count in n_grams.items():
                if count >= threshold:
                    return ToolGap(
                        kind=ToolGapKind.REPEATED_SEQUENCE,
                        description=f"Repeated manual sequence detected: {', '.join(seq)}",
                        suggested_tool_name=f"auto_{seq[0].replace(' ', '_')}",
                        evidence=list(seq)
                    )
                    
            n_grams.clear()
            
        return None
