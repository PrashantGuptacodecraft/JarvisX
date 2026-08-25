"""engine.py - Isolated Sandbox for Counter-Factual Simulations."""
import json
import copy
from .models import SimulationStatus, HypotheticalTransition, SimulationResult

class ImaginationPhysicsEngine:
    """Provides a sandbox to simulate state changes without affecting production state."""
    
    def simulate(
        self, 
        base_state_snapshot: dict,
        kg_edges: list,
        transitions: tuple[HypotheticalTransition, ...]
    ) -> SimulationResult:
        if len(transitions) > 50:
            return SimulationResult(SimulationStatus.FAILED, "Too many transitions", "{}")
            
        # Strict isolation: deep copy inputs to guarantee production state immutability
        sim_state = copy.deepcopy(base_state_snapshot)
        sim_kg = copy.deepcopy(kg_edges)
        
        try:
            for transition in transitions:
                if transition.action_type in ("tool_execution", "network_request", "event_bus_publish"):
                    # M34 Containment rules apply strictly in imagination too
                    return SimulationResult(
                        SimulationStatus.BLOCKED_BY_CONTAINMENT, 
                        f"Prohibited action in sandbox: {transition.action_type}", 
                        "{}"
                    )
                
                if transition.action_type == "mutate_state":
                    # deterministic mutation
                    sim_state[transition.target] = transition.payload
                elif transition.action_type == "add_kg_edge":
                    sim_kg.append((transition.target, transition.payload))
                else:
                    raise ValueError(f"Unknown hypothetical action: {transition.action_type}")
                    
            # Calculate delta safely
            modified_keys = [k for k in sim_state if k not in base_state_snapshot or base_state_snapshot[k] != sim_state[k]]
            
            delta = {
                "state_keys_modified": modified_keys,
                "new_kg_edges_count": len(sim_kg) - len(kg_edges)
            }
            
            return SimulationResult(
                status=SimulationStatus.SUCCESS,
                error_message=None,
                state_delta=json.dumps(delta)[:4096]
            )
            
        except Exception as e:
            return SimulationResult(
                status=SimulationStatus.FAILED,
                error_message=str(e)[:256],
                state_delta="{}"
            )
