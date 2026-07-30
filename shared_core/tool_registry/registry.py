import logging
from typing import Dict, List, Optional, Any

from .models import ToolSpec, ToolExecutionResult, ToolLifecycleState

log = logging.getLogger(__name__)

class ToolRegistry:
    """A registry that the brain dispatches tool calls through."""
    
    def __init__(self, event_bus: Optional[Any] = None):
        self._tools: Dict[str, ToolSpec] = {}
        self.event_bus = event_bus

    def register(self, tool: ToolSpec) -> bool:
        """Register a new ToolSpec. Returns False if already registered."""
        if tool.name in self._tools:
            log.warning(f"Tool {tool.name} already registered.")
            return False
        self._tools[tool.name] = tool
        
        if self.event_bus:
            try:
                self.event_bus.publish(
                    topic="tool.created",
                    source="tool_registry",
                    payload={
                        "tool_name": tool.name,
                        "description": tool.description
                    }
                )
            except Exception as e:
                log.error(f"Failed to publish tool.created event for {tool.name}: {e}")
                
        return True
        
    def update_state(self, name: str, state: ToolLifecycleState) -> bool:
        """Update the lifecycle state of a registered tool."""
        if name not in self._tools:
            return False
        self._tools[name].lifecycle_state = state
        return True

    def get_tool(self, name: str) -> Optional[ToolSpec]:
        """Retrieve a ToolSpec by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[ToolSpec]:
        """List all registered tools deterministically sorted by name."""
        return [self._tools[k] for k in sorted(self._tools.keys())]

    def dispatch(self, name: str, params: Dict[str, Any]) -> ToolExecutionResult:
        """Dispatch a tool call to its handler. Only ACTIVE tools can run."""
        tool = self.get_tool(name)
        if not tool:
            return ToolExecutionResult(success=False, error=f"Tool not found: {name}")
            
        if tool.lifecycle_state != ToolLifecycleState.ACTIVE:
            return ToolExecutionResult(
                success=False, 
                error=f"Tool {name} cannot run. Current state: {tool.lifecycle_state.value}"
            )
        
        try:
            return tool.handler(params)
        except Exception as e:
            log.error(f"Error executing tool {name}: {e}")
            return ToolExecutionResult(success=False, error=str(e))
