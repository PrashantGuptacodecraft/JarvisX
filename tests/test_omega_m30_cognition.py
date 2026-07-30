"""test_omega_m30_cognition.py - Focused tests for Milestone 30."""
import os
import time
import pytest
import shutil
from omega_core.cognition.models import (
    CognitionStatus, DecisionSummary, EvidenceReference, CognitionTrace
)
from omega_core.cognition.recorder import CognitionSession
from omega_core.cognition.persistence import CognitionPersistence, MAX_FILE_SIZE
from omega_core.cognition.continuity import OmegaCognitionContinuity
from omega_core.cognition.redaction import redact_text, hash_evidence_content

TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), "test_data_omega")

@pytest.fixture
def clean_persistence():
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)
    p = CognitionPersistence(base_dir=TEST_DATA_DIR)
    yield p
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)

def test_deterministic_trace_creation():
    session = CognitionSession("sess_123")
    assert session.status == CognitionStatus.CREATED
    
    t = session.add_trace(
        goal_id="g1", 
        problem_summary="Test problem", 
        decision=DecisionSummary(
            selected_strategy="test strategy",
            alternatives_considered=("alt1", "alt2"),
            decision="test decision",
            confidence=0.9,
            assumptions=("a1",),
            constraints=("c1",)
        )
    )
    
    assert t.session_id == "sess_123"
    assert t.goal_id == "g1"
    assert t.status == CognitionStatus.REASONING
    assert session.status == CognitionStatus.REASONING
    assert session.active_trace_id == t.trace_id

def test_secret_redaction():
    bad_summary = "Here is my secret AWS key AKIAIOSFODNN7EXAMPLE and my password db://user:pass123@host"
    safe = redact_text(bad_summary)
    assert "AKIAIOSFODNN7EXAMPLE" not in safe
    assert "pass123" not in safe
    assert "[REDACTED_AWS_KEY]" in safe
    assert "[REDACTED_PASSWORD]" in safe
    
    session = CognitionSession("sess_sec")
    t = session.add_trace("g", bad_summary)
    assert "AKIA" not in t.problem_summary
    assert "pass123" not in t.problem_summary

def test_checkpoint_creation_and_restoration(clean_persistence):
    continuity = OmegaCognitionContinuity(persistence=clean_persistence)
    session = CognitionSession("sess_chk")
    
    e1 = EvidenceReference(
        source_id="doc1", source_type="text", 
        excerpt="Important fact", content_sha256=hash_evidence_content("Important fact"),
        sensitivity="low", captured_at=time.time()
    )
    
    session.add_trace("g1", "prob", evidence=[e1])
    
    res = continuity.checkpoint(session)
    assert res.status == "SUCCESS"
    assert res.checkpoint_id.startswith("cp_")
    
    # Restore
    cont_res = continuity.restore("sess_chk")
    assert cont_res.error is None
    assert cont_res.continuation is not None
    assert cont_res.continuation.session_id == "sess_chk"
    assert cont_res.continuation.status == CognitionStatus.REASONING
    assert cont_res.continuation.restored_checkpoint_id == res.checkpoint_id
    assert cont_res.continuation.active_trace_id == session.active_trace_id

def test_corrupted_checkpoint_handling(clean_persistence):
    continuity = OmegaCognitionContinuity(persistence=clean_persistence)
    session = CognitionSession("sess_corr")
    session.add_trace("g", "prob")
    continuity.checkpoint(session)
    
    # Corrupt the latest file
    with open(os.path.join(TEST_DATA_DIR, "sessions", "sess_corr", "latest.json"), "w") as f:
        f.write("{invalid json")
        
    cont_res = continuity.restore("sess_corr")
    assert cont_res.continuation is None
    assert cont_res.error == "NOT_FOUND"

def test_capacity_limits(clean_persistence):
    continuity = OmegaCognitionContinuity(persistence=clean_persistence)
    session = CognitionSession("sess_cap")
    
    for i in range(55):
        session.add_trace("g", f"prob {i}", status=CognitionStatus.COMPLETED)
        
    res = continuity.checkpoint(session)
    assert res.status == "SUCCESS"
    assert res.compaction_occurred is True
    
    cont_res = continuity.restore("sess_cap")
    assert cont_res.continuation.diagnostics["traces_loaded"] == 50

def test_no_raw_chain_of_thought():
    session = CognitionSession("sess_len")
    with pytest.raises(ValueError, match="exceeds 500"):
        session.add_trace("g", "A" * 501)
        
    with pytest.raises(ValueError, match="exceeds 1024"):
        session.add_trace("g", "prob", outcome_summary="A" * 1025)
        
    with pytest.raises(ValueError, match="boolean"):
        DecisionSummary(
            selected_strategy="s", alternatives_considered=(), 
            decision="d", confidence=True, assumptions=(), constraints=()
        )
