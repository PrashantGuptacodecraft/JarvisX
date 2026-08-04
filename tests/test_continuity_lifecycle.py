"""test_continuity_lifecycle.py - Repeated focused lifecycle test for ContinuityManager."""
import os
import shutil
import tempfile
import threading
import pytest

from shared_core.state_manager.continuity import ContinuityManager

def test_continuity_rapid_lifecycle():
    # 7. repeat multiple times;
    for i in range(10):
        # 6. use temporary directory
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_state.json")
        
        try:
            # 1. start continuity;
            manager = ContinuityManager(path=db_path, autosave_interval=0.01)
            
            # Register dummy provider
            state = {"count": i}
            manager.register_provider("dummy", lambda: state, lambda v: state.update(v))
            
            manager.start_autosave()
            
            # 2. write state;
            state["count"] += 1
            
            # 3. request shutdown; 4. join owned thread with bounded timeout; 5. perform final atomic write;
            # manager.stop() executes all of this now that we fixed it.
            manager.stop(final_save=True)
            
            # Verify the snapshot was written
            assert os.path.exists(db_path)
            
        finally:
            # 6. immediately delete temporary directory;
            shutil.rmtree(temp_dir)
            
    # 8. confirm zero live project-owned threads (e.g. 'continuity-autosave')
    live_threads = [t.name for t in threading.enumerate()]
    assert "continuity-autosave" not in live_threads
