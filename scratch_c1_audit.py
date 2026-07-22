from memory.manager import MemoryManager as LegacyMemoryManager
from shared_core.memory_engine.manager import MemoryManager as CanonicalMemoryManager

assert LegacyMemoryManager is CanonicalMemoryManager
print("C1 Audit Part A: MemoryManager identity verified.")

from memory.rag_manager import RAGManager as LegacyRAGManager
from shared_core.memory_engine.rag_manager import RAGManager as CanonicalRAGManager

assert LegacyRAGManager is CanonicalRAGManager
print("C1 Audit Part A: RAGManager identity verified.")
