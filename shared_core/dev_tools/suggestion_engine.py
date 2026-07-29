from dataclasses import dataclass
from typing import List, Optional
from shared_core.memory_engine.manager import MemoryManager
from shared_core.memory_engine.kg_query import KGQueryService
from .event_models import DevEventEnvelope
from shared_core.event_bus.topics import PERCEPTION_DEV_SUGGESTIONS_GENERATED
from shared_core.event_bus.bus import EventBus
import time
import datetime

@dataclass
class CodeSuggestion:
    __test__ = False
    context_symbol: str
    suggested_action: str
    referenced_symbols: List[str]
    confidence: float

class AutonomousSuggester:
    """
    D12 - Autonomous code suggestions.
    Generates context-grounded suggestions using the code-KG (not blind LLM).
    """
    def __init__(self, memory_manager: MemoryManager, event_bus: Optional[EventBus] = None):
        self.memory = memory_manager
        self.query_service = KGQueryService(memory_manager)
        self.event_bus = event_bus

    def generate_suggestions(self, target_symbol: str) -> List[CodeSuggestion]:
        start_time = time.time()
        suggestions = []
        
        # We query the KG to find relationships around target_symbol
        # 1. Look for what it calls
        out_neighbors = self.query_service.neighbors(target_symbol, direction="out", relation_type="CALLS")
        for n in out_neighbors:
            suggestions.append(CodeSuggestion(
                context_symbol=target_symbol,
                suggested_action=f"Review callee '{n['neighbor']}' to ensure side-effects match '{target_symbol}' expectations.",
                referenced_symbols=[n['neighbor']],
                confidence=0.8
            ))

        # 2. Look for what depends on it
        in_neighbors = self.query_service.neighbors(target_symbol, direction="in", relation_type="depends_on")
        for n in in_neighbors:
            suggestions.append(CodeSuggestion(
                context_symbol=target_symbol,
                suggested_action=f"Update dependent module '{n['neighbor']}' to reflect changes in '{target_symbol}'.",
                referenced_symbols=[n['neighbor']],
                confidence=0.9
            ))

        # Sort for determinism
        suggestions.sort(key=lambda s: (s.confidence, s.suggested_action), reverse=True)
        
        if self.event_bus:
            duration_ms = (time.time() - start_time) * 1000
            env = DevEventEnvelope(
                schema_version=1,
                event_type=PERCEPTION_DEV_SUGGESTIONS_GENERATED,
                event_id=f"evt_{int(time.time()*1000)}",
                operation="suggestion_generation",
                request_id=None,
                repository_id=None,
                occurred_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                duration_ms=duration_ms,
                status="success",
                summary={
                    "target_symbol": target_symbol,
                    "suggestions_count": len(suggestions)
                }
            )
            self.event_bus.publish(PERCEPTION_DEV_SUGGESTIONS_GENERATED, env.to_dict())
            
        return suggestions
