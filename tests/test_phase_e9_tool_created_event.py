import pytest
from shared_core.event_bus.bus import EventBus
from shared_core.tool_registry.models import ToolSpec, ToolExecutionResult, ToolLifecycleState
from shared_core.tool_registry.registry import ToolRegistry

def test_tool_created_event_published():
    bus = EventBus()
    registry = ToolRegistry(event_bus=bus)
    
    events_received = []
    def on_event(event):
        events_received.append(event)
        
    bus.subscribe("tool.created", on_event, source="test_subscriber")
    
    spec = ToolSpec(
        name="test_tool",
        description="A test tool",
        params_schema={},
        handler=lambda p: ToolExecutionResult(success=True),
        lifecycle_state=ToolLifecycleState.ACTIVE
    )
    
    registry.register(spec)
    
    import time
    time.sleep(0.1) 
    
    assert len(events_received) == 1
    assert events_received[0].topic == "tool.created"
    assert events_received[0].payload["tool_name"] == "test_tool"
    assert events_received[0].payload["description"] == "A test tool"

def test_no_event_if_duplicate():
    bus = EventBus()
    registry = ToolRegistry(event_bus=bus)
    
    events_received = []
    def on_event(event):
        events_received.append(event)
        
    bus.subscribe("tool.created", on_event, source="test_subscriber")
    
    spec = ToolSpec(
        name="test_tool",
        description="A test tool",
        params_schema={},
        handler=lambda p: ToolExecutionResult(success=True),
        lifecycle_state=ToolLifecycleState.ACTIVE
    )
    
    # Register once
    registry.register(spec)
    
    import time
    time.sleep(0.1)
    assert len(events_received) == 1
    
    # Register duplicate
    registry.register(spec)
    time.sleep(0.1)
    
    assert len(events_received) == 1
