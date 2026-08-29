from communication_exchange_link import CommunicationExchangeLinkFlowMixin
from graph_model import OAGraph


def _add(graph: OAGraph, node_type: str, name: str, **attributes) -> str:
    ok, node_id, error = graph.add_node(node_type, name, **attributes)
    assert ok, error
    return node_id


class _Flow(CommunicationExchangeLinkFlowMixin):
    def __init__(self, model: OAGraph) -> None:
        self.model = model
        self.notices: list[str] = []

    def ask_yes_no(self, *_args, **_kwargs) -> bool:
        return True

    def ask_validated(self, **_kwargs) -> str:
        return "Radio link"

    def ask_choice(self, _question, choices, _why) -> str:
        return choices[0][0]

    def add_notice(self, message: str) -> None:
        self.notices.append(message)


def _base_interaction_model() -> tuple[OAGraph, str, str, str, str]:
    graph = OAGraph()
    soldier = _add(graph, "OperationalActor", "Soldier")
    detector = _add(
        graph,
        "OperationalEntity",
        "Threat detection system",
        expects_activity=True,
    )
    report = _add(graph, "OperationalActivity", "Report threat engagement")
    detect = _add(graph, "OperationalActivity", "Detect incoming threats")
    assert graph.add_relation(soldier, "PERFORMS", report)[0]
    assert graph.add_relation(detector, "PERFORMS", detect)[0]
    assert graph.add_relation(
        detect,
        "OPERATIONAL_EXCHANGE",
        report,
        name="Threat report",
    )[0]
    return graph, soldier, detector, report, detect


def _communication_data(graph: OAGraph):
    return [
        data
        for _source, _target, data in graph.graph.edges(data=True)
        if data.get("type") == "COMMUNICATION_MEAN"
    ]


def test_new_communication_mean_records_the_exchange_it_carries():
    graph, _soldier, _detector, report, detect = _base_interaction_model()
    _Flow(graph).capture_communication()

    communication = _communication_data(graph)
    assert len(communication) == 1
    assert communication[0]["name"] == "Radio link"
    assert communication[0]["exchange_refs"] == [
        {
            "source_activity_id": detect,
            "target_activity_id": report,
            "exchange_name": "Threat report",
        }
    ]


def test_existing_single_communication_mean_is_reused_and_linked_to_new_exchanges():
    graph, soldier, detector, report, detect = _base_interaction_model()
    assert graph.add_relation(
        detector,
        "COMMUNICATION_MEAN",
        soldier,
        name="Radio link",
    )[0]

    flow = _Flow(graph)
    flow.capture_communication()
    refs = _communication_data(graph)[0]["exchange_refs"]
    assert refs == [
        {
            "source_activity_id": detect,
            "target_activity_id": report,
            "exchange_name": "Threat report",
        }
    ]

    engage = _add(graph, "OperationalActivity", "Engage threats")
    assert graph.add_relation(soldier, "PERFORMS", engage)[0]
    assert graph.add_relation(
        detect,
        "OPERATIONAL_EXCHANGE",
        engage,
        name="Engagement command",
    )[0]

    flow.capture_communication()
    refs = _communication_data(graph)[0]["exchange_refs"]
    assert len(refs) == 2
    assert {
        "source_activity_id": detect,
        "target_activity_id": engage,
        "exchange_name": "Engagement command",
    } in refs
