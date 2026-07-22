from .manager import MemoryManager, STOP_WORDS

__all__ = ["MemoryManager", "STOP_WORDS", "RAGManager"]

def __getattr__(name):
    if name == "RAGManager":
        from .rag_manager import RAGManager
        return RAGManager
    raise AttributeError(name)
