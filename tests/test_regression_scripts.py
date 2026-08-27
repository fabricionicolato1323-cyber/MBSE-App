from __future__ import annotations

import importlib

import pytest


REGRESSION_MODULES = (
    "smoke_test",
    "goal_fast_path_test",
    "participant_classification_test",
    "participant_rules_test",
    "candidate_discovery_test",
    "semantic_frames_test",
    "ollama_service_test",
    "knowledge_graph_test",
)


@pytest.mark.parametrize("module_name", REGRESSION_MODULES)
def test_existing_regression_script(module_name: str) -> None:
    module = importlib.import_module(module_name)
    module.main()
