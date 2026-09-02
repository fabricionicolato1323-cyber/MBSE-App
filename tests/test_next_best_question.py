from __future__ import annotations

from graph_model import OAGraph
from next_best_question import best_next_question, rank_next_questions


def add_node(model: OAGraph, node_type: str, name: str, **attributes) -> str:
    ok, node_id, error = model.add_node(node_type, name, **attributes)
    assert ok, error
    return node_id


def connect(model: OAGraph, source: str, relation: str, target: str, **attributes) -> None:
    ok, error = model.add_relation(source, relation, target, **attributes)
    assert ok, error


def test_empty_model_starts_with_goal_before_other_questions():
    model = OAGraph()
    ranked = rank_next_questions(model)
    assert ranked[0].key == "missing_goal"
    assert ranked[0].priority == 100


def test_active_participant_without_action_is_prioritized():
    model = OAGraph()
    add_node(model, "OperationalCapability", "Protect the area")
    operator = add_node(model, "OperationalActor", "Operator")

    recommendation = best_next_question(model)
    assert recommendation is not None
    assert recommendation.key == "participant_without_action"
    assert recommendation.target_id == operator
    assert "Operator" in recommendation.action_label


def test_unowned_action_is_detected_after_other_participant_has_behavior():
    model = OAGraph()
    goal = add_node(model, "OperationalCapability", "Protect the area")
    operator = add_node(model, "OperationalActor", "Operator")
    owned = add_node(model, "OperationalActivity", "Monitor the area")
    unowned = add_node(model, "OperationalActivity", "Report the event")
    connect(model, operator, "PERFORMS", owned)
    connect(model, owned, "SUPPORTS_CAPABILITY", goal)

    recommendation = best_next_question(model)
    assert recommendation is not None
    assert recommendation.key == "action_without_performer"
    assert recommendation.target_id == unowned


def test_action_without_goal_is_detected_after_performer_is_known():
    model = OAGraph()
    goal = add_node(model, "OperationalCapability", "Protect the area")
    operator = add_node(model, "OperationalActor", "Operator")
    action = add_node(model, "OperationalActivity", "Monitor the area")
    connect(model, operator, "PERFORMS", action)

    recommendation = best_next_question(model)
    assert recommendation is not None
    assert recommendation.key == "action_without_goal"
    assert recommendation.target_id == action
    assert goal in model.nodes_of_type("OperationalCapability")


def test_cross_participant_exchange_recommends_missing_communication():
    model = OAGraph()
    goal = add_node(model, "OperationalCapability", "Coordinate access")
    operator = add_node(model, "OperationalActor", "Operator")
    visitor = add_node(model, "OperationalActor", "Visitor")
    authorize = add_node(model, "OperationalActivity", "Authorize access")
    enter = add_node(model, "OperationalActivity", "Enter facility")

    connect(model, operator, "PERFORMS", authorize)
    connect(model, visitor, "PERFORMS", enter)
    connect(model, authorize, "SUPPORTS_CAPABILITY", goal)
    connect(model, enter, "SUPPORTS_CAPABILITY", goal)
    connect(model, authorize, "OPERATIONAL_EXCHANGE", enter, name="Access permission")

    recommendation = best_next_question(model)
    assert recommendation is not None
    assert recommendation.key == "missing_communication"
    assert {recommendation.target_id, recommendation.secondary_id} == {operator, visitor}


def test_existing_communication_removes_that_gap():
    model = OAGraph()
    goal = add_node(model, "OperationalCapability", "Coordinate access")
    operator = add_node(model, "OperationalActor", "Operator")
    visitor = add_node(model, "OperationalActor", "Visitor")
    authorize = add_node(model, "OperationalActivity", "Authorize access")
    enter = add_node(model, "OperationalActivity", "Enter facility")

    connect(model, operator, "PERFORMS", authorize)
    connect(model, visitor, "PERFORMS", enter)
    connect(model, authorize, "SUPPORTS_CAPABILITY", goal)
    connect(model, enter, "SUPPORTS_CAPABILITY", goal)
    connect(model, authorize, "OPERATIONAL_EXCHANGE", enter, name="Access permission")
    connect(model, operator, "COMMUNICATION_MEAN", visitor, name="Voice")

    ranked_keys = [item.key for item in rank_next_questions(model)]
    assert "missing_communication" not in ranked_keys
    assert ranked_keys[0] == "review_characteristics"


def test_multiple_actions_without_exchange_get_low_priority_interaction_review():
    model = OAGraph()
    goal = add_node(model, "OperationalCapability", "Handle visitors")
    operator = add_node(model, "OperationalActor", "Operator")
    greet = add_node(model, "OperationalActivity", "Greet visitor")
    register = add_node(model, "OperationalActivity", "Register visitor")

    connect(model, operator, "PERFORMS", greet)
    connect(model, operator, "PERFORMS", register)
    connect(model, greet, "SUPPORTS_CAPABILITY", goal)
    connect(model, register, "SUPPORTS_CAPABILITY", goal)

    recommendation = best_next_question(model)
    assert recommendation is not None
    assert recommendation.key == "review_interactions"
    assert recommendation.priority == 45


def test_ignored_optional_review_moves_to_next_available_recommendation():
    model = OAGraph()
    goal = add_node(model, "OperationalCapability", "Handle visitors")
    operator = add_node(model, "OperationalActor", "Operator")
    greet = add_node(model, "OperationalActivity", "Greet visitor")
    register = add_node(model, "OperationalActivity", "Register visitor")

    connect(model, operator, "PERFORMS", greet)
    connect(model, operator, "PERFORMS", register)
    connect(model, greet, "SUPPORTS_CAPABILITY", goal)
    connect(model, register, "SUPPORTS_CAPABILITY", goal)

    first = best_next_question(model)
    assert first is not None and first.key == "review_interactions"
    second = best_next_question(model, ignored_identities={first.identity})
    assert second is not None
    assert second.key == "review_characteristics"
