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
    ``exchange_refs`` edge attribute records the activity-to-activity exchanges
    carried by that medium so the diagram can route:

        Activity -> Port -> Communication Mean -> Port -> Activity

    The association is always explicit. Even when exactly one Communication Mean
    already exists between the performers, the user may associate the exchange to
    it, create another Communication Mean, or leave the exchange unassigned.
    Older models without ``exchange_refs`` therefore remain editable without the
    app silently guessing which medium carries an interaction.
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

    @staticmethod
    def _edge_has_exchange_ref(
        edge: tuple[str, str, Any, dict[str, Any]],
        source_action: str,
        target_action: str,
        exchange_name: str,
    ) -> bool:
        reference = _exchange_ref(source_action, target_action, exchange_name)
        existing = edge[3].get("exchange_refs")
        refs = existing if isinstance(existing, list) else []
        return any(
            isinstance(item, dict) and _same_exchange_ref(item, reference)
            for item in refs
        )

    def _link_exchange_to_communication(
        self,
        edge: tuple[str, str, Any, dict[str, Any]],
        source_action: str,
        target_action: str,
        exchange_name: str,
    ) -> bool:
        source, target, key, data = edge
        reference = _exchange_ref(source_action, target_action, exchange_name)
        existing = data.get("exchange_refs")
        refs = [dict(item) for item in existing] if isinstance(existing, list) else []
        if any(_same_exchange_ref(item, reference) for item in refs):
            return False

        # Keep Undo semantics consistent with other graph mutations.
        checkpoint = getattr(self.model, "_checkpoint", None)
        if callable(checkpoint):
            checkpoint()
        self.model.graph[source][target][key]["exchange_refs"] = [*refs, reference]

        # Autosave graph variants persist accepted mutations through _persist().
        # This association changes an edge attribute directly rather than adding
        # an edge, so persist it explicitly when that hook is available.
        persist = getattr(self.model, "_persist", None)
        if callable(persist):
            persist()
        return True

    def _create_communication_for_exchange(
        self,
        source_participant: str,
        target_participant: str,
        source_action: str,
        target_action: str,
        exchange_name: str,
    ) -> None:
        source_name = self.model.name(source_participant)
        target_name = self.model.name(target_participant)
        medium = self.ask_validated(
            question="How do they communicate?",
            explanation=(
                "Name the real-world communication method, not software "
                "or implementation details."
            ),
            expected_concept="CommunicationMean",
            why=(
                "This records how two operational participants are able "
                "to support this specific interaction."
            ),
            context=(
                f"Participants: {source_name} and {target_name}. "
                f"Interaction: {exchange_name}."
            ),
        )

        reference = _exchange_ref(source_action, target_action, exchange_name)
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
            self.add_notice(f"Could not add the communication method: {error}")

    def _choose_communication_for_exchange(
        self,
        source_participant: str,
        target_participant: str,
        source_action: str,
        target_action: str,
        exchange_name: str,
    ) -> None:
        source_name = self.model.name(source_participant)
        target_name = self.model.name(target_participant)
        existing = self._communication_edges_between(
            source_participant,
            target_participant,
        )

        choices: list[tuple[str, str]] = []
        for index, edge in enumerate(existing):
            medium_name = str(edge[3].get("name") or "Communication method")
            if self._edge_has_exchange_ref(
                edge,
                source_action,
                target_action,
                exchange_name,
            ):
                medium_name = f"{medium_name} (already associated)"
            choices.append((f"existing:{index}", medium_name))

        choices.extend(
            [
                ("__new_communication__", "+ Add new communication method"),
                ("__no_communication__", "No communication method / leave unassigned"),
            ]
        )

        selected = self.ask_choice(
            (
                f"How should '{exchange_name}' be carried between "
                f"{source_name} and {target_name}?"
            ),
            choices,
            (
                "Choose an existing communication method to associate with this "
                "interaction, add another method, or explicitly leave it unassigned."
            ),
        )

        if selected == "__no_communication__":
            return
        if selected == "__new_communication__":
            self._create_communication_for_exchange(
                source_participant,
                target_participant,
                source_action,
                target_action,
                exchange_name,
            )
            return

        try:
            chosen = existing[int(selected.split(":", 1)[1])]
        except (IndexError, ValueError):
            self.add_notice("The selected communication method is no longer available.")
            return

        changed = self._link_exchange_to_communication(
            chosen,
            source_action,
            target_action,
            exchange_name,
        )
        medium_name = str(chosen[3].get("name") or "Communication method")
        if changed:
            self.add_notice(
                f"Associated interaction '{exchange_name}' with communication method: {medium_name}"
            )
        else:
            self.add_notice(
                f"Interaction '{exchange_name}' already uses communication method: {medium_name}"
            )

    def capture_communication_for_exchange(
        self,
        source_action: str,
        target_action: str,
        exchange_name: str,
    ) -> None:
        """Ask the Communication Mean question for one specific exchange only."""
        source_participants = self.model.participants_for_activity(source_action)
        target_participants = self.model.participants_for_activity(target_action)

        for source_participant in source_participants:
            for target_participant in target_participants:
                if source_participant == target_participant:
                    continue
                self._choose_communication_for_exchange(
                    source_participant,
                    target_participant,
                    source_action,
                    target_action,
                    exchange_name,
                )

    def capture_communication(self) -> None:
        """Review Communication Means exchange-by-exchange without guessing."""
        for source_action, target_action, exchange_name in self.model.exchanges():
            self.capture_communication_for_exchange(
                source_action,
                target_action,
                exchange_name,
            )
