import time
import statistics
import os
import sqlite3
from pathlib import Path

def run_probe():
    results = {}
    
    # 2. MemoryManager construction without triples
    def probe_mm_empty():
        from shared_core.memory_engine.manager import MemoryManager
        start = time.monotonic()
        mm = MemoryManager()
        mm.conn.close()
        return time.monotonic() - start
        
    res = [probe_mm_empty() for _ in range(5)]
    results["MemoryManager (Empty)"] = {"median": statistics.median(res), "max": max(res)}
    
    # 3. MemoryManager construction with a representative C4 graph
    try:
        os.remove("test_c4_graph.db")
    except:
        pass
    
    import shared_core.memory_engine.manager
    shared_core.memory_engine.manager.DB_PATH = Path("test_c4_graph.db")
    from shared_core.memory_engine.manager import MemoryManager
    mm = MemoryManager()
    for i in range(5000):
        mm.upsert_triple(f"Node{i}", "relates_to", f"Node{(i+1)%5000}")
    mm.conn.close()
    
    def probe_mm_full():
        start = time.monotonic()
        mm = MemoryManager()
        mm.conn.close()
        return time.monotonic() - start
        
    res = [probe_mm_full() for _ in range(5)]
    results["MemoryManager (5000 Triples)"] = {"median": statistics.median(res), "max": max(res)}
    
    # 4. Graph projection loading alone
    def probe_graph_load():
        mm = MemoryManager()
        start = time.monotonic()
        mm._load_kg_projection()
        dur = time.monotonic() - start
        mm.conn.close()
        return dur
        
    res = [probe_graph_load() for _ in range(5)]
    results["Graph Projection Loading (5000 Triples)"] = {"median": statistics.median(res), "max": max(res)}
    
    # 1. State/continuity restoration
    from shared_core.state_manager.manager import StateManager
    def probe_state():
        class MockBus:
            def subscribe(self, *a, **kw): pass
        start = time.monotonic()
        sm = StateManager(bus=MockBus())
        return time.monotonic() - start
        
    res = [probe_state() for _ in range(5)]
    results["State/Continuity Restoration"] = {"median": statistics.median(res), "max": max(res)}
    
    # 5. Complete headless build (only run once to save time, or 3 times)
    import main
    def probe_main():
        start = time.monotonic()
        res = main.build_jarvis()
        dur = time.monotonic() - start
        if isinstance(res, tuple):
            for x in res:
                if hasattr(x, "shutdown"): x.shutdown()
        elif hasattr(res, "shutdown"):
            res.shutdown()
        return dur
        
    res = [probe_main() for _ in range(3)]
    results["Complete Headless Build"] = {"median": statistics.median(res), "max": max(res)}
    
    print("\n\n===== BOOT BUDGET REPORT =====")
    for k, v in results.items():
        print(f"--- {k} ---")
        print(f"Median: {v['median']:.4f}s")
        print(f"Max:    {v['max']:.4f}s\n")

if __name__ == "__main__":
    run_probe()
