"""test_omega_m37_imagination.py - M37 tests."""
import pytest
from omega_core.imagination.models import HypotheticalTransition, SimulationResult, SimulationStatus
from omega_core.imagination.engine import ImaginationPhysicsEngine

def test_sandbox_isolation_and_mutation():
    engine = ImaginationPhysicsEngine()
    
    real_state = {"power": "on", "shield": "up"}
    real_kg = [("A", "knows", "B")]
    
    transitions = (
        HypotheticalTransition("mutate_state", "shield", "down"),
        HypotheticalTransition("add_kg_edge", "B", "knows_C")
    )
    
    result = engine.simulate(real_state, real_kg, transitions)
    
    assert result.status == SimulationStatus.SUCCESS
    assert "shield" in result.state_delta
    
    # PROVE IMMUTABILITY
    assert real_state["shield"] == "up" # unaffected
    assert len(real_kg) == 1 # unaffected

def test_containment_in_sandbox():
    engine = ImaginationPhysicsEngine()
    transitions = (
        HypotheticalTransition("tool_execution", "system", "format C:"),
    )
    result = engine.simulate({}, [], transitions)
    
    assert result.status == SimulationStatus.BLOCKED_BY_CONTAINMENT
    assert "Prohibited action" in result.error_message

def test_bounds_enforced():
    with pytest.raises(ValueError):
        HypotheticalTransition("A" * 70, "target", "payload")
