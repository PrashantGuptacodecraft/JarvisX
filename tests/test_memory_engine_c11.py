import pytest
import datetime
from typing import Dict, Any

from shared_core.memory_engine.manager import MemoryManager
from shared_core.memory_engine.kg_query import KGQueryService
from shared_core.memory_engine.relation_types import RelationType
from shared_core.memory_engine.entity_types import EntityType
from shared_core.memory_engine.consolidation_predicates import ConsolidationPredicate

@pytest.fixture
def test_setup(tmp_path, monkeypatch):
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', tmp_path / "jarvis_c11.db")
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    
    memory = MemoryManager()
    query_service = KGQueryService(memory)
    
    return memory, query_service

def test_c11_habit_edges_queryable(test_setup):
    memory, query_service = test_setup
    
    # 1. Promote a semantic pattern manually
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
    
    # 2. Wait for graph projection to catch up (it's synchronous in test usually, but just in case)
    graph = query_service._ensure_projection()
    assert graph is not None
    
    # 3. Test neighbors() querying using new RelationType enums
    edges = query_service.neighbors("User", direction="out", relation_type=ConsolidationPredicate.HAS_RECURRING_PATTERN)
    assert len(edges) == 1
    assert edges[0]["neighbor"] == "habit:semantic:user_action_123"
    assert edges[0]["predicate"] == ConsolidationPredicate.HAS_RECURRING_PATTERN
    
    # 4. Test the new get_actor_habits API
    habits = query_service.get_actor_habits("User")
    
    assert len(habits) == 1
    habit = habits[0]
    
    assert habit["habit_id"] == "habit:semantic:user_action_123"
    assert habit["actor"] == "User"
    assert habit["action"] == "literal:action:jump"
    assert habit["outcome"] == "literal:outcome:success"
    assert habit["targets"] == ["mario"]
    assert habit["evidence"] == ["event:action:1", "event:action:2", "event:action:3"]
    
    # 5. Check missing actor
    missing = query_service.get_actor_habits("UnknownUser")
    assert len(missing) == 0
