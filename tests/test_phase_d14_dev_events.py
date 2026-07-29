import pytest
import time
from pathlib import Path

from shared_core.event_bus.bus import EventBus
from shared_core.event_bus.subscription import SYNC
from shared_core.event_bus import topics
from shared_core.dev_tools.dependency_analyzer import DependencyAnalyzer
from shared_core.dev_tools.call_analyzer import CallAnalyzer
from shared_core.dev_tools.architecture_analyzer import ArchitectureAnalyzer
from shared_core.dev_tools.architecture_query import ArchitectureQuery
from shared_core.dev_tools.architecture_model import ArchitectureSnapshot
from shared_core.dev_tools.autonomous_test_runner import AutonomousTestRunner
from shared_core.dev_tools.test_execution_model import TestExecutionRequest, TestFramework
from shared_core.dev_tools.execution_gateway import ExecutionGateway, PreRunAssessment
from shared_core.dev_tools.regression_bisection import RegressionBisector, BisectionRequest
from shared_core.dev_tools.refactoring_engine import RefactoringEngine, RefactoringRequest, RefactoringOperation
from shared_core.dev_tools.suggestion_engine import AutonomousSuggester
from shared_core.dev_tools.style_application import StyleApplication
from shared_core.dev_tools.style_analyzer import StyleAnalyzer
from shared_core.dev_tools.style_model import CodingStyleModel
from shared_core.memory_engine.manager import MemoryManager

def test_d14_topics_exist():
    assert hasattr(topics, "PERCEPTION_DEV_DEPENDENCY_GRAPH_GENERATED")
    assert hasattr(topics, "PERCEPTION_DEV_CALL_GRAPH_GENERATED")
    assert hasattr(topics, "PERCEPTION_DEV_ARCHITECTURE_SNAPSHOT_GENERATED")
    assert hasattr(topics, "PERCEPTION_DEV_ARCHITECTURE_DRIFT_DETECTED")
    assert hasattr(topics, "PERCEPTION_DEV_TESTS_COMPLETED")
    assert hasattr(topics, "PERCEPTION_DEV_BISECTION_COMPLETED")
    assert hasattr(topics, "PERCEPTION_DEV_REFACTORING_EVALUATED")
    assert hasattr(topics, "PERCEPTION_DEV_SUGGESTIONS_GENERATED")
    assert hasattr(topics, "PERCEPTION_DEV_STYLE_VALIDATION_COMPLETED")
    assert hasattr(topics, "PERCEPTION_DEV_CODING_STYLE_GENERATED")

def test_d14_dependency_analyzer_emits(tmp_path):
    eb = EventBus()
    events = []
    eb.subscribe(topics.PERCEPTION_DEV_DEPENDENCY_GRAPH_GENERATED, lambda e: events.append(e), mode=SYNC)
    
    analyzer = DependencyAnalyzer(tmp_path, event_bus=eb)
    analyzer.analyze()
    
    assert len(events) == 1
    assert events[0].payload["event_type"] == topics.PERCEPTION_DEV_DEPENDENCY_GRAPH_GENERATED
    assert "nodes_count" in events[0].payload["summary"]
    
def test_d14_style_analyzer_emits(tmp_path):
    eb = EventBus()
    events = []
    eb.subscribe(topics.PERCEPTION_DEV_CODING_STYLE_GENERATED, lambda e: events.append(e), mode=SYNC)
    
    analyzer = StyleAnalyzer(str(tmp_path), event_bus=eb)
    analyzer.analyze()
    
    assert len(events) == 1
    assert events[0].payload["event_type"] == topics.PERCEPTION_DEV_CODING_STYLE_GENERATED

def test_d14_style_application_emits():
    eb = EventBus()
    events = []
    eb.subscribe(topics.PERCEPTION_DEV_STYLE_VALIDATION_COMPLETED, lambda e: events.append(e), mode=SYNC)
    
    app = StyleApplication(CodingStyleModel(), event_bus=eb)
    app.validate_code("print('hello')\n")
    
    assert len(events) == 1
    assert events[0].payload["event_type"] == topics.PERCEPTION_DEV_STYLE_VALIDATION_COMPLETED
    assert "is_valid" in events[0].payload["summary"]

def test_d14_architecture_analyzer_emits(tmp_path):
    eb = EventBus()
    events = []
    eb.subscribe(topics.PERCEPTION_DEV_ARCHITECTURE_SNAPSHOT_GENERATED, lambda e: events.append(e), mode=SYNC)
    
    analyzer = ArchitectureAnalyzer(tmp_path, event_bus=eb)
    analyzer.analyze()
    
    assert len(events) == 1
    assert events[0].payload["event_type"] == topics.PERCEPTION_DEV_ARCHITECTURE_SNAPSHOT_GENERATED

def test_d14_architecture_drift_emits():
    eb = EventBus()
    events = []
    eb.subscribe(topics.PERCEPTION_DEV_ARCHITECTURE_DRIFT_DETECTED, lambda e: events.append(e), mode=SYNC)
    
    old_snap = ArchitectureSnapshot({}, [], [], [], [])
    new_snap = ArchitectureSnapshot({}, [], [], [], [])
    
    ArchitectureQuery.compare(old_snap, new_snap, event_bus=eb)
    
    assert len(events) == 1
    assert events[0].payload["event_type"] == topics.PERCEPTION_DEV_ARCHITECTURE_DRIFT_DETECTED

class DummyGateway(ExecutionGateway):
    def __init__(self, eb):
        super().__init__(event_bus=eb, workspace_root=".", evidence_store=None, predictors=[])
    def execute(self, req, run_callback):
        return run_callback()

def test_d14_test_runner_emits(tmp_path):
    eb = EventBus()
    events = []
    eb.subscribe(topics.PERCEPTION_DEV_TESTS_COMPLETED, lambda e: events.append(e), mode=SYNC)
    
    gw = DummyGateway(eb)
    runner = AutonomousTestRunner(gw, event_bus=eb)
    
    req = TestExecutionRequest(
        request_id="1", 
        repository_root=str(tmp_path), 
        selected_framework=TestFramework.PYTEST.value, 
        selected_command=["echo", "pytest"], 
        working_directory=str(tmp_path)
    )
    
    runner.execute(req)
    assert len(events) == 1
    assert events[0].payload["event_type"] == topics.PERCEPTION_DEV_TESTS_COMPLETED

