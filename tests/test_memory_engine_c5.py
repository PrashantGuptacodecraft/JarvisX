import pytest
from shared_core.memory_engine.manager import MemoryManager
from shared_core.memory_engine.entity_types import EntityType

@pytest.fixture
def memory_manager(tmp_path, monkeypatch):
    db_path = tmp_path / "jarvis_c5.db"
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', db_path)
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    return MemoryManager()

def test_c5_entity_types_creatable(memory_manager):
    """C5 Acceptance: Person/Project/File/App/Command/Tool/Event/Habit creatable and typed."""
    # Create one of each to prove they are creatable and typed
    memory_manager.register_entity("Alice", EntityType.PERSON)
    memory_manager.register_entity("JarvisX", EntityType.PROJECT)
    memory_manager.register_entity("main.py", EntityType.FILE)
    memory_manager.register_entity("VSCode", EntityType.APP)
    memory_manager.register_entity("git_commit", EntityType.COMMAND)
    memory_manager.register_entity("bash", EntityType.TOOL)
    memory_manager.register_entity("Boot", EntityType.EVENT)
    memory_manager.register_entity("MorningRoutine", EntityType.HABIT)

    # Verify they can be queried
    persons = memory_manager.get_entities_by_type(EntityType.PERSON)
    assert "Alice" in persons
    
    projects = memory_manager.get_entities_by_type(EntityType.PROJECT)
    assert "JarvisX" in projects

def test_c5_enum_enforcement(memory_manager):
    """Proves that EntityType constraints are enforced in the API."""
    with pytest.raises(ValueError, match="must be an instance of EntityType"):
        memory_manager.register_entity("Bob", "Person") # type: ignore (string instead of enum)

def test_c5_typing_uses_triple_store(memory_manager):
    """Proves the entity typing maps cleanly to the triple store."""
    memory_manager.register_entity("Bob", EntityType.PERSON)
    
    # Check via raw triples
    triples = memory_manager.query_triples(subject="Bob", predicate="type", object="Person")
    assert len(triples) == 1
    assert triples[0]["subject"] == "Bob"
    assert triples[0]["predicate"] == "type"
    assert triples[0]["object"] == "Person"
