from __future__ import annotations

from typing import Any


def _exchange_ref(source_action: str, target_action: str, exchange_name: str) -> dict[str, str]:
    return {
        "source_activity_id": source_action,
        "target_activity_id": target_action,
        "exchange_name": exchange_name,
    }


def _same_exchange_ref(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left.get("source_activity_id") == right.get("source_activity_id")
        and left.get("target_activity_id") == right.get("target_activity_id")
        and str(left.get("exchange_name") or "").strip().casefold()
        == str(right.get("exchange_name") or "").strip().casefold()
    )


class CommunicationExchangeLinkFlowMixin:
    """Persist which Operational Exchange uses each Communication Mean.

    Communication Means remain participant-to-participant relations. The
    `exchange_refs` edge attribute records the activity-to-activity exchanges
    carried by that medium so the diagram can route:

        Activity -> Port -> Communication Mean -> Port -> Activity

    Old models without `exchange_refs` remain valid and are handled by a
    deterministic diagram fallback when exactly one medium connects the two
    performers.
    """

    def _communication_edges_between(
        self,
        first_participant: str,
        second_participant: str,
    ) -> list[tuple[str, str, Any, dict[str, Any]]]:
        result: list[tuple[str, str, Any, dict[str, Any]]] = []
        for source, target, key, data in self.model.graph.edges(keys=True, data=True):
            if data.get("type") != "COMMUNICATION_MEAN":
                continue
            if {source, target} != {first_participant, second_participant}:
                continue
            result.append((source, target, key, data))
        return result

    def _link_exchange_to_communication(
        self,
        edge: tuple[str, str, Any, dict[str, Any]],
        source_action: str,
        target_action: str,
        exchange_name: str,
    ) -> None:
        source, target, key, data = edge
        reference = _exchange_ref(source_action, target_action, exchange_name)
        existing = data.get("exchange_refs")
        refs = [dict(item) for item in existing] if isinstance(existing, list) else []
        if any(_same_exchange_ref(item, reference) for item in refs):
            return

        # Keep Undo semantics consistent with other graph mutations.
        checkpoint = getattr(self.model, "_checkpoint", None)
        if callable(checkpoint):
            checkpoint()
        self.model.graph[source][target][key]["exchange_refs"] = [*refs, reference]

    def _choose_existing_communication(
        self,
        edges: list[tuple[str, str, Any, dict[str, Any]]],
        exchange_name: str,
    ) -> tuple[str, str, Any, dict[str, Any]]:
        if len(edges) == 1:
            return edges[0]

        choices = [
            (str(index), str(data.get("name") or "Communication mean"))
            for index, (_source, _target, _key, data) in enumerate(edges)
        ]
        selected = self.ask_choice(
            f"Which communication method carries '{exchange_name}'?",
            choices,
            "Choose the communication method that carries this specific interaction.",
        )
        return edges[int(selected)]

    def capture_communication(self) -> None:
        for source_action, target_action, exchange_name in self.model.exchanges():
            source_participants = self.model.participants_for_activity(source_action)
            target_participants = self.model.participants_for_activity(target_action)

            for source_participant in source_participants:
                for target_participant in target_participants:
                    if source_participant == target_participant:
                        continue

                    existing = self._communication_edges_between(
                        source_participant,
                        target_participant,
                    )
                    if existing:
                        chosen = self._choose_existing_communication(existing, exchange_name)
                        self._link_exchange_to_communication(
                            chosen,
                            source_action,
                            target_action,
                            exchange_name,
                        )
                        continue

                    source_name = self.model.name(source_participant)
                    target_name = self.model.name(target_participant)
                    if not self.ask_yes_no(
                        f"Do {source_name} and {target_name} use a "
                        f"communication method for '{exchange_name}'?",
                        "If the interaction crosses between different participants, "
                        "the communication method may be important operationally.",
                    ):
                        continue

                    medium = self.ask_validated(
                        question="How do they communicate?",
                        explanation=(
                            "Name the real-world communication method, not software "
                            "or implementation details."
                        ),
                        expected_concept="CommunicationMean",
                        why=(
                            "This records how two operational participants are able "
                            "to interact."
                        ),
                        context=(
                            f"Participants: {source_name} and {target_name}. "
                            f"Interaction: {exchange_name}."
                        ),
                    )

                    reference = _exchange_ref(
                        source_action,
                        target_action,
                        exchange_name,
                    )
                    ok, error = self.model.add_relation(
                        source_participant,
                        "COMMUNICATION_MEAN",
                        target_participant,
                        name=medium,
                        exchange_refs=[reference],
                    )
                    if ok:
                        self.add_notice(f"Added communication method: {medium}")
                    else:
                        self.add_notice(
                            f"Could not add the communication method: {error}"
                        )
