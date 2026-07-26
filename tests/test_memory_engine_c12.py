import pytest
import time
from typing import Dict, Any

from shared_core.memory_engine.manager import MemoryManager
from shared_core import get_bus
from shared_core.event_bus.topics import MEMORY_KG_UPDATE

@pytest.fixture
def test_setup(tmp_path, monkeypatch):
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', tmp_path / "jarvis_c12.db")
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    
    memory = MemoryManager()
    return memory

def test_c12_kg_change_events_published(test_setup):
    memory = test_setup
    
    received_events = []
    
    def on_kg_update(event):
        received_events.append(event)
        
    bus = get_bus()
    subscription = bus.subscribe(MEMORY_KG_UPDATE, on_kg_update)
    
    try:
        # Upsert a triple
        memory.upsert_triple("SubjectA", "works_on", "ProjectB")
        
        # Wait a tiny bit for async dispatch if applicable (though in these tests it's mostly synchronous dispatch depending on EventBus impl)
        # EventBus in this system usually runs dispatch on the same thread or a worker thread.
        time.sleep(0.1)
        
        assert len(received_events) >= 1
        
        last_event = received_events[-1]
        assert last_event.topic == MEMORY_KG_UPDATE
        assert last_event.payload["subject"] == "SubjectA"
        assert last_event.payload["predicate"] == "works_on"
        assert last_event.payload["object"] == "ProjectB"
        assert last_event.payload["action"] == "upsert"
        assert "triple_id" in last_event.payload
        
        # Test promote_semantic_pattern
        received_events.clear()
        
        pattern = {
            "habit_id": "habit:semantic:user_action_123",
            "actor": "User",
            "action": "jump",
            "outcome": "success",
            "targets": ["mario"],
            "evidence": ["event:action:1", "event:action:2", "event:action:3"]
        }
        
        success = memory.promote_semantic_pattern(pattern)
        assert success is True
        
        time.sleep(0.1)
        
        assert len(received_events) > 0
        
        # Verify that we got events for the pattern edges
        found_actor_edge = False
        for ev in received_events:
            if ev.payload["predicate"] == "has_recurring_pattern":
                found_actor_edge = True
                
        assert found_actor_edge, "Expected an event for has_recurring_pattern"
        
    finally:
        bus.unsubscribe(subscription)
