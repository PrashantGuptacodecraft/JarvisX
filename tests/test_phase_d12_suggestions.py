import pytest
from shared_core.memory_engine.manager import MemoryManager
from shared_core.dev_tools.suggestion_engine import AutonomousSuggester, CodeSuggestion

@pytest.fixture
def memory():
    # Use memory memory-db
    mm = MemoryManager()
    mm.conn.execute("DELETE FROM facts")
    
    # Insert some dummy triples to form the code-KG
    mm.upsert_triple("func_A", "CALLS", "func_B", weight=1.0)
    mm.upsert_triple("module_X", "depends_on", "func_A", weight=1.0)
    
    # Reload projection so queries work
    mm._load_kg_projection()
    
    return mm

def test_autonomous_suggester_generates_context_grounded_suggestions(memory):
    suggester = AutonomousSuggester(memory)
    
    # Test on func_A
    suggestions = suggester.generate_suggestions("func_A")
    
    assert len(suggestions) == 2
    
    # Check depends_on suggestion
    dep_sug = next(s for s in suggestions if "module_X" in s.referenced_symbols)
    assert dep_sug.context_symbol == "func_A"
    assert "module_X" in dep_sug.suggested_action
    
    # Check CALLS suggestion
    call_sug = next(s for s in suggestions if "func_B" in s.referenced_symbols)
    assert call_sug.context_symbol == "func_A"
    assert "func_B" in call_sug.suggested_action
