"""integration.py - Concept Formation Integration with EventBus."""
import time
import logging
from typing import Optional
import threading

from shared_core.event_bus.bus import EventBus
from shared_core.event_bus.event import Event
from shared_core.event_bus.subscription import ASYNC
from shared_core.memory_engine.manager import MemoryManager
from .miner import CrossDomainIsomorphismMiner

log = logging.getLogger(__name__)

class ConceptFormationIntegration:
    def __init__(self, bus: EventBus, memory: MemoryManager):
        self.bus = bus
        self.miner = CrossDomainIsomorphismMiner(memory)
        self._sub = None
        self._last_run = 0.0
        self._cooldown_seconds = 60.0
        self._lock = threading.Lock()

    def start(self):
        # We listen to KG updates. To prevent spamming, we use async delivery and debounce.
        self._sub = self.bus.subscribe(
            pattern="memory.kg.update",
            handler=self._on_kg_update,
            mode=ASYNC,
            source="omega_concept_miner"
        )
        log.info("Concept Formation integration started.")

    def stop(self):
        if self._sub:
            self.bus.unsubscribe(self._sub)
            self._sub = None
        log.info("Concept Formation integration stopped.")

    def _on_kg_update(self, event: Event):
        now = time.time()
        with self._lock:
            if now - self._last_run < self._cooldown_seconds:
                return
            self._last_run = now
            
        try:
            concepts = self.miner.mine_concepts()
            for concept in concepts:
                self.bus.publish(
                    topic="omega.concept.formed",
                    source="concept_miner",
                    payload={
                        "concept_id": concept.concept_id,
                        "name": concept.name,
                        "motif_signature": concept.motif.structural_signature,
                        "instance_count": len(concept.instances)
                    }
                )
        except Exception as e:
            log.error(f"Concept formation failed: {e}")
