import logging
from typing import Optional, Protocol
from pathlib import Path
from .gap_model import ToolGap
from .tool_generator import ToolGenerator
from .sandbox_validator import ToolValidator
from .registry import ToolRegistry
from .models import ToolSpec, ToolLifecycleState

logger = logging.getLogger(__name__)

class SecurityApprover(Protocol):
    def approve(self, tool_code: str, spec: ToolSpec) -> bool:
        ...

class HumanConfirmationProvider(Protocol):
    def confirm(self, spec: ToolSpec) -> bool:
        ...

class ToolFactory:
    def __init__(
        self, 
        generator: ToolGenerator, 
        validator: ToolValidator, 
        registry: ToolRegistry, 
        security_approver: Optional[SecurityApprover] = None,
        human_confirmer: Optional[HumanConfirmationProvider] = None,
        persistence_dir: Optional[Path] = None
    ):
        self.generator = generator
        self.validator = validator
        self.registry = registry
        self.security_approver = security_approver
        self.human_confirmer = human_confirmer
        self.persistence_dir = persistence_dir
        
        if self.persistence_dir:
            self.persistence_dir.mkdir(parents=True, exist_ok=True)
            self._load_persisted_tools()
            
    def _load_persisted_tools(self):
        if not self.persistence_dir:
            return
            
        for path in self.persistence_dir.glob("*.py"):
            try:
                code = path.read_text(encoding="utf-8")
                namespace = {}
                exec(code, namespace)
                get_spec = namespace.get("get_tool_spec")
                if get_spec:
                    spec = get_spec()
                    # Persisted tools reload as ACTIVE assuming they were already approved
                    # But if we wanted we could re-verify them. For now just set active.
                    spec.lifecycle_state = ToolLifecycleState.ACTIVE
                    self.registry.register(spec)
            except Exception as e:
                logger.error(f"Failed to load persisted tool {path.name}: {e}")
        
    def build_and_register(self, gap: ToolGap) -> Optional[ToolSpec]:
        """
        End-to-end pipeline: generate, validate, security-check, confirm, and register.
        """
        # 1. Generate
        tool_code = self.generator.generate_tool_module(gap)
        
        # 2. Validate
        is_valid = self.validator.validate(tool_code, gap)
        if not is_valid:
            logger.warning(f"Tool generation failed validation for gap: {gap.description}")
            return None
            
        # 3. Load dynamically (since it passed sandbox)
        namespace = {}
        try:
            exec(tool_code, namespace)
            get_spec = namespace.get("get_tool_spec")
            if not get_spec:
                logger.warning("Tool module missing get_tool_spec")
                return None
                
            spec = get_spec()
        except Exception as e:
            logger.error(f"Failed to load generated tool: {e}")
            return None
            
        spec.lifecycle_state = ToolLifecycleState.VALIDATED
        
        # 4. Security Approval
        if not self.security_approver:
            spec.lifecycle_state = ToolLifecycleState.SECURITY_REJECTED
            logger.warning(f"Tool {spec.name} rejected: no security approver configured.")
            return spec
            
        if not self.security_approver.approve(tool_code, spec):
            spec.lifecycle_state = ToolLifecycleState.SECURITY_REJECTED
            logger.warning(f"Tool {spec.name} rejected by security layer.")
            return spec
        spec.lifecycle_state = ToolLifecycleState.SECURITY_APPROVED
            
        # 5. Human Confirmation
        if not self.human_confirmer:
            spec.lifecycle_state = ToolLifecycleState.CONFIRMATION_PENDING
            logger.warning(f"Tool {spec.name} pending: no human confirmer configured.")
            return spec
            
        spec.lifecycle_state = ToolLifecycleState.CONFIRMATION_PENDING
        if not self.human_confirmer.confirm(spec):
            spec.lifecycle_state = ToolLifecycleState.USER_REJECTED
            logger.warning(f"Tool {spec.name} rejected by user.")
            return spec
            
        # If it passed all gates, it becomes active
        spec.lifecycle_state = ToolLifecycleState.ACTIVE
            
        # 6. Register
        success = self.registry.register(spec)
        if success:
            if self.persistence_dir:
                file_path = self.persistence_dir / f"{spec.name}.py"
                file_path.write_text(tool_code, encoding="utf-8")
            return spec
        return None
