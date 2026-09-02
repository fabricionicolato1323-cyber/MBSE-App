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

    New decisions are explicit. For backward compatibility, an older model that
    has exactly one Communication Mean between two performers may still have
    exchanges that predate ``exchange_refs``. The first explicit association
    migrates those unambiguous legacy exchanges to refs instead of making them
    disappear from the Communication Mean presentation.
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

    def _operational_exchange_edges(
        self,
        source_action: str | None = None,
        target_action: str | None = None,
        exchange_name: str | None = None,
    ) -> list[tuple[str, str, Any, dict[str, Any]]]:
        result: list[tuple[str, str, Any, dict[str, Any]]] = []
        wanted_name = str(exchange_name or "").strip().casefold()
        for source, target, key, data in self.model.graph.edges(keys=True, data=True):
            if data.get("type") != "OPERATIONAL_EXCHANGE":
                continue
            if source_action is not None and source != source_action:
                continue
            if target_action is not None and target != target_action:
                continue
            if wanted_name and str(data.get("name") or "").strip().casefold() != wanted_name:
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

    def _unlink_exchange_from_communications(
        self,
        source_action: str,
        target_action: str,
        exchange_name: str,
        *,
        keep_edge: tuple[str, str, Any] | None = None,
    ) -> bool:
        """Remove stale medium references for one exchange.

        The guided flow asks for one communication decision for an exchange at
        a time. Changing that decision must therefore remove the old explicit
        reference instead of leaving contradictory ``exchange_refs`` behind.
        """
        reference = _exchange_ref(source_action, target_action, exchange_name)
        changed = False
        for source, target, key, data in self.model.graph.edges(keys=True, data=True):
            if data.get("type") != "COMMUNICATION_MEAN":
                continue
            if keep_edge is not None and (source, target, key) == keep_edge:
                continue
            existing = data.get("exchange_refs")
            if not isinstance(existing, list) or not existing:
                continue
            refs = [
                dict(item)
                for item in existing
                if isinstance(item, dict) and not _same_exchange_ref(item, reference)
            ]
            if len(refs) == len(existing):
                continue
            self.model.graph[source][target][key]["exchange_refs"] = refs
            changed = True
        return changed

    def _legacy_exchange_refs_for_communication(
        self,
        edge: tuple[str, str, Any, dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Recover old implicit assignments only when the medium is unambiguous."""
        source_participant, target_participant, _key, data = edge
        existing = data.get("exchange_refs")
        if isinstance(existing, list) and existing:
            return []
        if len(self._communication_edges_between(source_participant, target_participant)) != 1:
            return []

        refs: list[dict[str, str]] = []
        for source_action, target_action, _exchange_key, exchange in self._operational_exchange_edges():
            if str(exchange.get("communication_assignment") or "").casefold() == "none":
                continue
            source_participants = set(self.model.participants_for_activity(source_action))
            target_participants = set(self.model.participants_for_activity(target_action))
            matches = (
                source_participant in source_participants
                and target_participant in target_participants
            ) or (
                target_participant in source_participants
                and source_participant in target_participants
            )
            if not matches:
                continue
            reference = _exchange_ref(
                source_action,
                target_action,
                str(exchange.get("name") or "Exchange"),
            )
            if not any(_same_exchange_ref(item, reference) for item in refs):
                refs.append(reference)
        return refs

    def _set_exchange_communication_assignment(
        self,
        source_action: str,
        target_action: str,
        exchange_name: str,
        value: str,
        *,
        checkpoint: bool,
        persist: bool,
    ) -> None:
        matching = self._operational_exchange_edges(
            source_action,
            target_action,
            exchange_name,
        )
        if not matching:
            return
        if checkpoint:
            checkpoint_fn = getattr(self.model, "_checkpoint", None)
            if callable(checkpoint_fn):
                checkpoint_fn()
        for source, target, key, _data in matching:
            self.model.graph[source][target][key]["communication_assignment"] = value
        if persist:
            persist_fn = getattr(self.model, "_persist", None)
            if callable(persist_fn):
                persist_fn()

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
        refs_before = [dict(item) for item in existing] if isinstance(existing, list) else []
        legacy_refs = self._legacy_exchange_refs_for_communication(edge) if not refs_before else []
        already_linked = any(_same_exchange_ref(item, reference) for item in refs_before)

        # Keep Undo semantics consistent with other graph mutations. Replacing
        # an old medium reference and assigning the selected one are one user
        # decision and therefore share one checkpoint.
        checkpoint = getattr(self.model, "_checkpoint", None)
        if callable(checkpoint):
            checkpoint()
        self._unlink_exchange_from_communications(
            source_action,
            target_action,
            exchange_name,
            keep_edge=(source, target, key),
        )

        current = self.model.graph[source][target][key].get("exchange_refs")
        refs = [dict(item) for item in current] if isinstance(current, list) else []
        if not refs and legacy_refs:
            refs.extend(legacy_refs)
        if not any(_same_exchange_ref(item, reference) for item in refs):
            refs.append(reference)
        self.model.graph[source][target][key]["exchange_refs"] = refs
        self._set_exchange_communication_assignment(
            source_action,
            target_action,
            exchange_name,
            "assigned",
            checkpoint=False,
            persist=False,
        )

        persist = getattr(self.model, "_persist", None)
        if callable(persist):
            persist()
        return not already_linked

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
            created_edges = [
                edge
                for edge in self._communication_edges_between(source_participant, target_participant)
                if str(edge[3].get("name") or "").strip().casefold() == medium.strip().casefold()
                and self._edge_has_exchange_ref(edge, source_action, target_action, exchange_name)
            ]
            keep_edge = (
                (created_edges[-1][0], created_edges[-1][1], created_edges[-1][2])
                if created_edges
                else None
            )
            self._unlink_exchange_from_communications(
                source_action,
                target_action,
                exchange_name,
                keep_edge=keep_edge,
            )
            # add_relation already checkpointed the user decision; keep the
            # Operational Exchange marker consistent without adding another one.
            self._set_exchange_communication_assignment(
                source_action,
                target_action,
                exchange_name,
                "assigned",
                checkpoint=False,
                persist=True,
            )
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
            checkpoint = getattr(self.model, "_checkpoint", None)
            if callable(checkpoint):
                checkpoint()
            self._unlink_exchange_from_communications(
                source_action,
                target_action,
                exchange_name,
            )
            self._set_exchange_communication_assignment(
                source_action,
                target_action,
                exchange_name,
                "none",
                checkpoint=False,
                persist=True,
            )
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
