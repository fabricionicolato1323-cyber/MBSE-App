from __future__ import annotations

import builtins
from unittest.mock import patch

from current_scope import (
    filter_current_scope_comparison,
    format_current_scope_comparison,
)
from graph_model import OAGraph
from knowledge_graph import ModelComparison, ValidationIssue
from presentation import friendly_model_view
from review_flow import ReviewWorkflowMixin


def build_generic_model() -> OAGraph:
    model = OAGraph()
    _, goal_parent, _ = model.add_node("OperationalCapability", "Achieve outcome A")
    _, goal_child, _ = model.add_node("OperationalCapability", "Achieve outcome B")
    _, group, _ = model.add_node(
        "OperationalEntity",
        "Participant Group A",
        expects_activity=True,
        nature="team_or_collective",
    )
    _, role, _ = model.add_node("OperationalActor", "Participant Role A")
    _, action_parent, _ = model.add_node("OperationalActivity", "Perform action A")
    _, action_child, _ = model.add_node("OperationalActivity", "Perform action B")

    assert model.add_relation(goal_parent, "DECOMPOSES", goal_child)[0]
    assert model.add_relation(group, "CONTAINS", role)[0]
    assert model.add_relation(role, "PERFORMS", action_parent)[0]
    assert model.add_relation(role, "PERFORMS", action_child)[0]
    assert model.add_relation(action_parent, "DECOMPOSES", action_child)[0]
    assert model.add_relation(action_parent, "SUPPORTS_CAPABILITY", goal_parent)[0]
    assert model.add_relation(action_child, "SUPPORTS_CAPABILITY", goal_child)[0]
    assert model.add_characteristic(
        action_parent,
        {
            "name": "Duration",
            "value_type": "range",
            "lower_bound": 2,
            "upper_bound": 5,
            "unit": "minutes",
        },
    )[0]
    return model


def test_presentation() -> None:
    view = friendly_model_view(build_generic_model())
    assert "Participant Group A — team or collective" in view
    assert "Duration: 2 .. 5 minutes" in view
    assert "Composition / decomposition" in view
    assert "OperationalEntity" not in view
    assert "OperationalActor" not in view
    assert "team_or_collective" not in view
    assert "\nStructure\n" not in view


def test_current_scope_filter() -> None:
    comparison = ModelComparison(
        conforms=True,
        issues=(
            ValidationIssue(
                "WARNING",
                "goal-a",
                "Goal A",
                "The capability is not related to an operational mission.",
                "OperationalCapabilityShape",
            ),
            ValidationIssue(
                "INFO",
                "item-a",
                "Item A",
                "The interaction item does not yet reference domain data or concepts; this may limit content analysis.",
                "InteractionItemShape",
            ),
            ValidationIssue(
                "WARNING",
                "action-a",
                "Action A",
                "Current-scope warning.",
                "CurrentScopeShape",
            ),
        ),
        project_triples=42,
        elapsed_ms=12.5,
    )
    filtered = filter_current_scope_comparison(comparison)
    assert len(filtered.issues) == 1
    text = format_current_scope_comparison(filtered)
    assert "Current-scope warning." in text
    assert "Project RDF" not in text
    assert "goal-a" not in text


class _ReviewHarness(ReviewWorkflowMixin):
    def __init__(self) -> None:
        self.review_reached = False
        self.current_why = ""
        self.notice = ""

    def capture_goals(self):
        return []

    def capture_goal_candidates(self, goals):
        return None

    def capture_participants_and_actions(self):
        return None

    def capture_structure_and_environment(self):
        return None

    def capture_interactions(self):
        return None

    def capture_communication(self):
        return None

    def add_notice(self, message: str) -> None:
        self.notice = message

    def draw_question(self, *args, **kwargs) -> None:
        self.review_reached = True

    def command(self, value: str) -> bool:
        if value == "/quit":
            raise SystemExit(0)
        return False


def test_review_loop_is_reached() -> None:
    app = _ReviewHarness()
    with patch.object(builtins, "input", return_value="/quit"):
        try:
            app.run()
        except SystemExit:
            pass
    assert app.review_reached


def main() -> None:
    test_presentation()
    test_current_scope_filter()
    test_review_loop_is_reached()
    print("Workflow review test passed (3 checks).")


if __name__ == "__main__":
    main()
