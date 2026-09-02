from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NextBestQuestion:
    """One domain-neutral recommendation derived from the approved model state."""

    key: str
    priority: int
    action_label: str
    why: str
    target_id: str | None = None
    secondary_id: str | None = None

    @property
    def identity(self) -> str:
        parts = [self.key]
        if self.target_id:
            parts.append(self.target_id)
        if self.secondary_id:
            parts.append(self.secondary_id)
        return ":".join(parts)


def _node_has_characteristics(model, node_id: str) -> bool:
    getter = getattr(model, "characteristics_for_node", None)
    if not callable(getter):
        return False
    return bool(getter(node_id))


def _exchange_has_characteristics(model) -> bool:
    records = getattr(model, "exchange_records", None)
    getter = getattr(model, "characteristics_for_exchange", None)
    if not callable(records) or not callable(getter):
        return False
    for source_id, target_id, edge_key, _ in records():
        if getter(source_id, target_id, edge_key):
            return True
    return False


def rank_next_questions(model) -> list[NextBestQuestion]:
    """Rank the next useful questions without modifying the model.

    The ranking deliberately separates structural gaps from optional refinement.
    High-priority items are directly supported by deterministic graph rules;
    interaction and characteristic reviews are lower-priority prompts that can be
    skipped after the user has reviewed them once.
    """

    goals = list(model.nodes_of_type("OperationalCapability"))
    participants = list(model.participants())
    active_participants = list(model.active_participants())
    actions = list(model.nodes_of_type("OperationalActivity"))
    exchanges = list(model.exchanges())

    recommendations: list[NextBestQuestion] = []

    if not goals:
        recommendations.append(
            NextBestQuestion(
                key="missing_goal",
                priority=100,
                action_label="Add the missing goal",
                why="The model needs a desired outcome before the remaining behavior can be judged in context.",
            )
        )

    if not participants:
        recommendations.append(
            NextBestQuestion(
                key="missing_participant",
                priority=95,
                action_label="Add a participant or context element",
                why="The model does not yet identify who or what is involved.",
            )
        )

    for participant_id in active_participants:
        if model.actions_for_participant(participant_id):
            continue
        recommendations.append(
            NextBestQuestion(
                key="participant_without_action",
                priority=90,
                action_label=f"Describe what {model.name(participant_id)} does",
                why="An active participant has no behavior associated with it yet.",
                target_id=participant_id,
            )
        )

    for action_id in actions:
        if not model.participants_for_activity(action_id):
            recommendations.append(
                NextBestQuestion(
                    key="action_without_performer",
                    priority=88,
                    action_label=f"Assign '{model.name(action_id)}' to a participant",
                    why="Every action needs an explicit performer.",
                    target_id=action_id,
                )
            )

    if goals:
        for action_id in actions:
            if any(
                model.has_relation(action_id, "SUPPORTS_CAPABILITY", goal_id)
                for goal_id in goals
            ):
                continue
            recommendations.append(
                NextBestQuestion(
                    key="action_without_goal",
                    priority=82,
                    action_label=f"Connect '{model.name(action_id)}' to a goal",
                    why="The action is not yet connected to the outcome it helps achieve.",
                    target_id=action_id,
                )
            )

    # Communication is recommended only when an existing exchange crosses
    # participant boundaries. This avoids asking for communication means merely
    # because two participants exist in the same model.
    seen_communication_gaps: set[tuple[str, str]] = set()
    for source_action, target_action, _ in exchanges:
        source_performers = model.participants_for_activity(source_action)
        target_performers = model.participants_for_activity(target_action)
        for source_participant in source_performers:
            for target_participant in target_performers:
                if source_participant == target_participant:
                    continue
                pair = tuple(sorted((source_participant, target_participant)))
                if pair in seen_communication_gaps:
                    continue
                if model.has_communication_between(source_participant, target_participant):
                    continue
                seen_communication_gaps.add(pair)
                recommendations.append(
                    NextBestQuestion(
                        key="missing_communication",
                        priority=72,
                        action_label=(
                            f"Add how {model.name(source_participant)} and "
                            f"{model.name(target_participant)} communicate"
                        ),
                        why="An existing interaction crosses participant boundaries but no communication method is recorded.",
                        target_id=source_participant,
                        secondary_id=target_participant,
                    )
                )

    if len(actions) >= 2 and not exchanges:
        recommendations.append(
            NextBestQuestion(
                key="review_interactions",
                priority=45,
                action_label="Review whether the actions exchange anything",
                why="The model has multiple actions but no recorded interaction between them.",
            )
        )

    has_characteristics = any(_node_has_characteristics(model, node_id) for node_id in goals + participants + actions)
    has_characteristics = has_characteristics or _exchange_has_characteristics(model)
    if (goals or participants or actions or exchanges) and not has_characteristics:
        recommendations.append(
            NextBestQuestion(
                key="review_characteristics",
                priority=20,
                action_label="Review relevant characteristics or limits",
                why="No measurable limit, range, or descriptive characteristic has been captured yet.",
            )
        )

    recommendations.sort(key=lambda item: (-item.priority, item.identity))
    return recommendations


def best_next_question(
    model,
    *,
    ignored_identities: set[str] | None = None,
) -> NextBestQuestion | None:
    ignored = ignored_identities or set()
    for recommendation in rank_next_questions(model):
        if recommendation.identity not in ignored:
            return recommendation
    return None
