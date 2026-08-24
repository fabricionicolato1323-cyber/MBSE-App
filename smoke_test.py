import json
import tempfile
from pathlib import Path

from graph_model import OAGraph
from ontology import CONCEPT_GUIDANCE, NODE_TYPES, RELATION_GUIDANCE


def add(model: OAGraph, concept: str, name: str, description: str) -> str:
    ok, node_id, error = model.add_node(concept, name, description)
    assert ok, error
    return node_id


def main() -> None:
    model = OAGraph()
    assert not model.add_node(
        "OperationalActivity",
        "Create Python script",
        "Implementation-biased behavior.",
    )[0]
    assert not model.add_node(
        "OperationalEntity",
        "Unnamed Context",
        "",
    )[0]
    capability = add(
        model,
        "OperationalCapability",
        "Maintain secure access",
        "Keep authorized operations available while preventing unauthorized entry.",
    )
    actor = add(
        model,
        "OperationalActor",
        "Field Coordinator",
        "Human role responsible for coordinating field access decisions.",
    )
    team = add(
        model,
        "OperationalEntity",
        "Field Patrol Team",
        "Operational group that observes and protects the restricted area.",
    )
    area = add(
        model,
        "OperationalEntity",
        "Restricted Area",
        "Physical area whose access is controlled during operations.",
    )
    verify = add(
        model,
        "OperationalActivity",
        "Verify access authorization",
        "Confirm that a presented authorization permits entry.",
    )
    permit = add(
        model,
        "OperationalActivity",
        "Permit authorized entry",
        "Allow an authorized participant to enter the restricted area.",
    )
    exchange = add(
        model,
        "OperationalExchange",
        "Access authorization data",
        "Authorization evidence transferred from verification to entry control.",
    )
    communication = add(
        model,
        "CommunicationMean",
        "Voice radio communication",
        "Operational voice channel between the field team and coordinator.",
    )

    for source, relation, target in (
        (team, "CONTAINS", actor),
        (team, "LOCATED_IN", area),
        (actor, "PERFORMS", verify),
        (team, "PERFORMS", permit),
        (actor, "INVOLVED_IN_CAPABILITY", capability),
        (verify, "SUPPORTS_CAPABILITY", capability),
        (permit, "SUPPORTS_CAPABILITY", capability),
        (exchange, "SOURCE_ACTIVITY", verify),
        (exchange, "TARGET_ACTIVITY", permit),
        (communication, "SOURCE_PARTICIPANT", actor),
        (communication, "TARGET_PARTICIPANT", team),
        (communication, "SUPPORTS_EXCHANGE", exchange),
    ):
        ok, error = model.add_relation(source, relation, target)
        assert ok, error

    child = add(
        model,
        "OperationalActivity",
        "Check authorization validity",
        "Check that authorization dates and scope remain valid.",
    )
    assert model.add_relation(verify, "DECOMPOSES_INTO", child)[0]
    assert model.add_relation(actor, "PERFORMS", child)[0]
    assert not model.add_relation(child, "DECOMPOSES_INTO", verify)[0]
    assert not model.add_relation(exchange, "SOURCE_ACTIVITY", permit)[0]
    assert not model.add_relation(actor, "CONTAINS", team)[0]

    parameter = {
        "id": "parameter-area",
        "name": "Protected area",
        "description": "Maximum area covered by this operational capability.",
        "quantityKind": "area",
        "valueType": "Real",
        "unit": "km2",
    }
    constraint = {
        "id": "constraint-area",
        "name": "Maximum protected area",
        "description": "The protected area must not exceed the agreed coverage.",
        "parameterId": "parameter-area",
        "operator": "MAX",
        "value": "25",
        "scope": "HIERARCHY",
        "aggregation": "SUM",
        "applicableCondition": "Normal operations",
        "rationale": "Customer operational boundary",
    }
    stable_id = capability
    ok, error = model.update_node(
        capability,
        name="Maintain controlled access",
        parameters=[parameter],
        constraints=[constraint],
    )
    assert ok, error
    assert capability == stable_id
    assert model.graph.nodes[capability]["name"] == "Maintain controlled access"
    assert not model.update_node(capability, id="replacement-id")[0]

    assert set(CONCEPT_GUIDANCE) == NODE_TYPES
    assert all(item.get("definition") and item.get("example") for item in CONCEPT_GUIDANCE.values())
    assert all(item.get("definition") and item.get("example") for item in RELATION_GUIDANCE.values())
    assert not model.completeness_messages(), model.completeness_messages()

    with tempfile.TemporaryDirectory() as directory:
        path = model.save(str(Path(directory) / "model.json"))
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["schema_version"] == 2
        assert set(document["ontology"]["concepts"]) == NODE_TYPES
        assert document["ontology"]["relationships"]["PERFORMS"]["example"]
        loaded = OAGraph()
        loaded.load(str(path))
        assert loaded.name(stable_id) == "Maintain controlled access"
        assert loaded.graph.number_of_nodes() == model.graph.number_of_nodes()
        assert loaded.graph.number_of_edges() == model.graph.number_of_edges()

    print("Smoke test passed.")


if __name__ == "__main__":
    main()
