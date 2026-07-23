import pytest
from shared_core.memory_engine.manager import MemoryManager
from shared_core.memory_engine.relation_types import RelationType
from shared_core.memory_engine.entity_types import EntityType

@pytest.fixture
def memory_manager(tmp_path, monkeypatch):
    db_path = tmp_path / "jarvis_c6.db"
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', db_path)
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    return MemoryManager()

def test_c6_relation_types_insertable(memory_manager):
    """C6 Acceptance: Relation types operational and insertable."""
    memory_manager.register_entity("Alice", EntityType.PERSON)
    memory_manager.register_entity("JarvisX", EntityType.PROJECT)
    
    # works_on
    memory_manager.add_relation("Alice", RelationType.WORKS_ON, "JarvisX")
    
    # authored_by
    memory_manager.add_relation("main.py", RelationType.AUTHORED_BY, "Alice")

    # Verify they are correctly typed in triple store
    relations = memory_manager.get_relations(subject="Alice", relation_type=RelationType.WORKS_ON)
    assert len(relations) == 1
    assert relations[0]["object"] == "JarvisX"
    
    relations = memory_manager.get_relations(relation_type=RelationType.AUTHORED_BY, object="Alice")
    assert len(relations) == 1
    assert relations[0]["subject"] == "main.py"

def test_c6_enum_enforcement(memory_manager):
    """Proves that RelationType constraints are enforced in the API."""
    with pytest.raises(ValueError, match="relation_type must be an instance of RelationType"):
        memory_manager.add_relation("Alice", "works_on", "Project") # type: ignore

    with pytest.raises(ValueError, match="relation_type must be an instance of RelationType"):
        memory_manager.get_relations(relation_type="works_on") # type: ignore

def test_c6_traversable(memory_manager):
    """Proves the relations can be traversed both forwards and backwards."""
    memory_manager.add_relation("FileA", RelationType.DEPENDS_ON, "FileB")
    memory_manager.add_relation("FileA", RelationType.DEPENDS_ON, "FileC")
    memory_manager.add_relation("FileX", RelationType.DEPENDS_ON, "FileB")
    
    # Traverse forward from FileA
    forward = memory_manager.get_relations(subject="FileA", relation_type=RelationType.DEPENDS_ON)
    objects = {rel["object"] for rel in forward}
    assert objects == {"FileB", "FileC"}
    
    # Traverse backward from FileB
    backward = memory_manager.get_relations(object="FileB", relation_type=RelationType.DEPENDS_ON)
    subjects = {rel["subject"] for rel in backward}
    assert subjects == {"FileA", "FileX"}
