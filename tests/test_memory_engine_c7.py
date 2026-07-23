import pytest
import datetime
from shared_core.memory_engine.manager import MemoryManager
from shared_core.memory_engine.execution_history import ExecutionRecorder
from shared_core.memory_engine.execution_predicates import ExecutionPredicate
from shared_core.memory_engine.entity_types import EntityType
from shared_core.event_bus.bus import EventBus
from shared_core.event_bus.topics import ACTION_RESULT, COGNITION_TRACE

@pytest.fixture
def test_setup(tmp_path, monkeypatch):
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', tmp_path / "jarvis_c7.db")
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    
    bus = EventBus()
    memory = MemoryManager()
    recorder = ExecutionRecorder(memory, bus)
    
    return memory, bus, recorder

def test_c7_lifecycle_and_exact_once_subscriptions(test_setup):
    memory, bus, recorder = test_setup
    assert not recorder._is_started
    
    # 1. Start subscribes exactly once
    recorder.start()
    assert recorder._is_started
    subs = [s for s in bus._subs if s.pattern == ACTION_RESULT]
    assert any(sub.source == "execution_recorder" for sub in subs)
    
    # 2. Repeated start does not duplicate
    recorder.start()
    subs_after = [s for s in bus._subs if s.pattern == ACTION_RESULT]
    # the count of execution_recorder subs should be 1
    assert len([s for s in subs_after if s.source == "execution_recorder"]) == 1
    
    # 3. Stop removes subscriptions
    recorder.stop()
    subs_stop = [s for s in bus._subs if s.pattern == ACTION_RESULT]
    assert not any(sub.source == "execution_recorder" for sub in subs_stop)
    assert not recorder._is_started

def test_c7_action_result_creates_event_entity(test_setup):
    memory, bus, recorder = test_setup
    
    payload = {
        "action": "open_app",
        "actor": "user1",
        "outcome": "success",
        "target": "Spotify",
        "timestamp": "2026-07-23T10:00:00Z"
    }
    
    # Send mock event
    class MockEvent:
        def __init__(self):
            self.payload = payload
            self.timestamp = "2026-07-23T10:00:00Z"
            self.source = "test"
            self.topic = ACTION_RESULT
            
    recorder._handle_action_result(MockEvent())
    
    # Verify entity creation
    entities = memory.get_entities_by_type(EntityType.EVENT)
    assert len(entities) == 1
    event_id = entities[0]
    
    # Verify relations
    who = memory.query_triples(subject=event_id, predicate=ExecutionPredicate.PERFORMED_BY)
    assert who[0]["object"] == "user1"
    
    what = memory.query_triples(subject=event_id, predicate=ExecutionPredicate.ACTION)
    assert what[0]["object"] == "open_app"
    
    outcome = memory.query_triples(subject=event_id, predicate=ExecutionPredicate.OUTCOME)
    assert outcome[0]["object"] == "literal:outcome:success"
    
    target = memory.query_triples(subject=event_id, predicate=ExecutionPredicate.TARGET)
    assert target[0]["object"] == "Spotify"
    
    when = memory.query_triples(subject=event_id, predicate=ExecutionPredicate.OCCURRED_AT)
    assert when[0]["object"] == "2026-07-23T10:00:00Z"

def test_c7_cognition_trace_creates_event_entity(test_setup):
    memory, bus, recorder = test_setup
    payload = {
        "step": "think",
        "source": "AI",
        "outcome": "completed",
        "trace_id": "trace-123",
        "span_id": "span-1",
        "timestamp": "2026-07-23T10:05:00Z"
    }
    
    class MockEvent:
        def __init__(self):
            self.payload = payload
            self.timestamp = "2026-07-23T10:05:00Z"
            self.source = "test"
            self.topic = COGNITION_TRACE
            
    recorder._handle_cognition_trace(MockEvent())
    
    entities = memory.get_entities_by_type(EntityType.EVENT)
    assert len(entities) == 1
    event_id = entities[0]
    assert event_id == "event:trace:trace-123_span-1" # Deterministic ID
    
    who = memory.query_triples(subject=event_id, predicate=ExecutionPredicate.PERFORMED_BY)
    assert who[0]["object"] == "AI"
    
    what = memory.query_triples(subject=event_id, predicate=ExecutionPredicate.ACTION)
    assert what[0]["object"] == "think"

def test_c7_idempotent_duplicate_delivery(test_setup):
    memory, bus, recorder = test_setup
    
    payload = {
        "action": "open_app",
        "actor": "user1",
        "timestamp": "2026-07-23T10:00:00Z",
        "event_id": "stable-id-456"
    }
    
    class MockEvent:
        def __init__(self):
            self.payload = payload
            self.timestamp = "2026-07-23T10:00:00Z"
            self.source = "test"
            
    # Send twice
    recorder._handle_action_result(MockEvent())
    recorder._handle_action_result(MockEvent())
    
    entities = memory.get_entities_by_type(EntityType.EVENT)
    assert len(entities) == 1 # Idempotent, no duplicate
    
    actions = memory.query_triples(subject="event:action:stable-id-456", predicate=ExecutionPredicate.ACTION)
    assert len(actions) == 1

def test_c7_missing_required_fields_skipped(test_setup):
    memory, bus, recorder = test_setup
    
    # Missing action should not crash, should simply return
    payload = {
        "actor": "user1",
        "timestamp": "2026-07-23T10:00:00Z"
    }
    class MockEvent:
        def __init__(self):
            self.payload = payload
            self.timestamp = "2026-07-23T10:00:00Z"
            self.source = "test"
            
    recorder._handle_action_result(MockEvent())
    
    entities = memory.get_entities_by_type(EntityType.EVENT)
    assert len(entities) == 0

def test_c7_transaction_atomic_rollback(test_setup):
    memory, bus, recorder = test_setup
    
    payload = {
        "action": "test_action",
        "timestamp": "2026-07-23T10:00:00Z"
    }
    
    # Inject failure into upsert_triple_cursor
    original_upsert = memory._upsert_triple_cursor
    
    def failing_upsert(*args, **kwargs):
        if args[2] == ExecutionPredicate.OUTCOME:
            raise RuntimeError("Injected database failure")
        return original_upsert(*args, **kwargs)
        
    memory._upsert_triple_cursor = failing_upsert
    
    class MockEvent:
        def __init__(self):
            self.payload = payload
            self.timestamp = "2026-07-23T10:00:00Z"
            self.source = "test"
            
    recorder._handle_action_result(MockEvent())
    
    # Because of rollback, NO triples for this event should exist at all
    all_triples = memory.query_triples(predicate="type", object=EntityType.EVENT.value)
    assert len(all_triples) == 0
    
    # Projection should be clean too
    assert memory.kg_projection.number_of_nodes() == 0 if hasattr(memory.kg_projection, "number_of_nodes") else True

def test_c7_oversized_payload_truncation(test_setup):
    memory, bus, recorder = test_setup
    
    huge_str = "A" * 2000
    payload = {
        "action": huge_str,
        "target": ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12"],
        "timestamp": "2026-07-23T10:00:00Z"
    }
    
    class MockEvent:
        def __init__(self):
            self.payload = payload
            self.timestamp = "2026-07-23T10:00:00Z"
            self.source = "test"
            
    recorder._handle_action_result(MockEvent())
    
    entities = memory.get_entities_by_type(EntityType.EVENT)
    assert len(entities) == 1
    event_id = entities[0]
    
    # Truncated string
    action = memory.query_triples(subject=event_id, predicate=ExecutionPredicate.ACTION)
    assert len(action[0]["object"]) == 1000
    
    # Bounded targets list
    targets = memory.query_triples(subject=event_id, predicate=ExecutionPredicate.TARGET)
    assert len(targets) == 10

def test_c7_sensitive_fields_excluded(test_setup):
    memory, bus, recorder = test_setup
    payload = {
        "action": "login",
        "timestamp": "2026-07-23T10:00:00Z",
        "password": "supersecretpassword",
        "api_key": "sk-123456",
        "token": "jwt-token-abcd"
    }
    
    class MockEvent:
        def __init__(self):
            self.payload = payload
            self.timestamp = "2026-07-23T10:00:00Z"
            self.source = "test"
            self.topic = ACTION_RESULT
            
    recorder._handle_action_result(MockEvent())
    
    # Verify no sensitive data is in the database at all
    all_objects = memory.conn.execute("SELECT object FROM kg_triples").fetchall()
    objects_str = str(all_objects)
    
    assert "supersecretpassword" not in objects_str
    assert "sk-123456" not in objects_str
    assert "jwt-token-abcd" not in objects_str

def test_c7_conflicting_duplicate_rejected(test_setup):
    memory, bus, recorder = test_setup
    payload1 = {
        "action": "open_app",
        "timestamp": "2026-07-23T10:00:00Z",
        "event_id": "conflict-id"
    }
    
    class MockEvent1:
        def __init__(self):
            self.payload = payload1
            self.timestamp = "2026-07-23T10:00:00Z"
            self.source = "test"
            self.topic = ACTION_RESULT
            
    recorder._handle_action_result(MockEvent1())
    
    payload2 = {
        "action": "close_app",
        "timestamp": "2026-07-23T10:05:00Z",
        "event_id": "conflict-id"
    }
    
    class MockEvent2:
        def __init__(self):
            self.payload = payload2
            self.timestamp = "2026-07-23T10:05:00Z"
            self.source = "test"
            self.topic = ACTION_RESULT
            
    recorder._handle_action_result(MockEvent2())
    
    # Verify only open_app exists, close_app was rejected
    actions = memory.query_triples(subject="event:action:conflict-id", predicate=ExecutionPredicate.ACTION)
    assert len(actions) == 1
    assert actions[0]["object"] == "open_app"
