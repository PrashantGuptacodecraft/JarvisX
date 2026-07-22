from memory.manager import MemoryManager as LegacyMemoryManager
from shared_core.memory_engine.manager import MemoryManager as CanonicalMemoryManager

from memory.rag_manager import RAGManager as LegacyRAGManager
from shared_core.memory_engine.rag_manager import RAGManager as CanonicalRAGManager

def test_memory_manager_identity():
    assert LegacyMemoryManager is CanonicalMemoryManager

def test_rag_manager_identity():
    assert LegacyRAGManager is CanonicalRAGManager

def test_memory_manager_persistence_paths():
    mgr = CanonicalMemoryManager()
    # It should still create jarvis.db in data directory
    assert "jarvis.db" in str(mgr.db_path)
    
def test_rag_manager_persistence_paths():
    mgr = CanonicalRAGManager()
    # If ChromaDB initializes, it should use data/chroma
    if mgr.collection is not None:
        assert "data" in str(mgr.client.get_settings().persist_directory) or "chroma" in str(mgr.client.get_settings().persist_directory)
