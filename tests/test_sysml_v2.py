from __future__ import annotations

import copy
import unittest
from pathlib import Path

import sysml_v2
from arcadia_oa_library import (
    ArcadiaOALibrary,
    DEFAULT_ARCADIA_OA_LIBRARY,
    validate_arcadia_oa_library,
)
from sysml_v2 import ARCADIA_OA_LIBRARY_TEXT, generate_sysml_v2


def sample_payload() -> dict:
    return {
        "directed": True,
        "multigraph": True,
        "graph": {
            "model": "Arcadia Operational Analysis",
            "model_name": "Threat response OA",
        },
        "nodes": [
            {
                "id": "cap:respond",
                "type": "OperationalCapability",
                "name": "Respond to threat",
            },
            {
                "id": "entity:center",
                "type": "OperationalEntity",
                "name": "Control Center",
            },
            {
                "id": "actor:operator",
                "type": "OperationalActor",
                "name": "Operator",
            },
            {
                "id": "activity:detect",
                "type": "OperationalActivity",
                "name": "Detect Threat",
                "characteristics": [
                    {
                        "name": "Latency",
                        "value_type": "number",
                        "value": 2.5,
                        "unit": "s",
                    }
                ],
            },
            {
                "id": "activity:assess",
                "type": "OperationalActivity",
                "name": "Assess Threat",
            },
        ],
        "edges": [
            {
                "source": "entity:center",
                "target": "actor:operator",
                "key": 0,
                "type": "CONTAINS",
            },
            {
                "source": "actor:operator",
                "target": "activity:detect",
                "key": 0,
                "type": "PERFORMS",
            },
            {
                "source": "entity:center",
                "target": "activity:assess",
                "key": 0,
                "type": "PERFORMS",
            },
            {
                "source": "activity:detect",
                "target": "activity:assess",
                "key": 0,
                "type": "OPERATIONAL_EXCHANGE",
                "name": "Threat Information",
            },
            {
                "source": "actor:operator",
                "target": "entity:center",
                "key": 0,
                "type": "COMMUNICATION_MEAN",
                "name": "Radio",
            },
        ],
    }


def sample_scenario() -> dict:
    return {
        "id": "OperationalScenario:nominal",
        "name": "Nominal response",
        "valid": True,
        "issues": [],
        "steps": [
            {
                "order": 1,
                "kind": "activity",
                "activity_id": "activity:detect",
            },
            {
                "order": 2,
                "kind": "interaction",
                "source_activity_id": "activity:detect",
                "target_activity_id": "activity:assess",
                "edge_key": 0,
                "exchange_name": "Threat Information",
                "communication_mean": {
                    "source_participant_id": "actor:operator",
                    "target_participant_id": "entity:center",
                    "edge_key": 0,
                    "name": "Radio",
                },
            },
            {
                "order": 3,
                "kind": "activity",
                "activity_id": "activity:assess",
            },
        ],
    }


class SysMLV2GenerationTests(unittest.TestCase):
    def test_library_bundle_is_the_translation_authority(self) -> None:
        contract = DEFAULT_ARCADIA_OA_LIBRARY.contract
        self.assertEqual(contract["policy"]["semantic_fallback"], "forbidden")
        self.assertEqual(contract["relationships"]["CONTAINS"]["strategy"], "nested_usage")
        self.assertEqual(contract["relationships"]["DECOMPOSES"]["strategy"], "nested_usage")
        self.assertEqual(contract["relationships"]["LOCATED_IN"]["strategy"], "reference")
        self.assertEqual(contract["relationships"]["SUPPORTS_CAPABILITY"]["strategy"], "allocation")
        self.assertEqual(contract["relationships"]["OPERATIONAL_EXCHANGE"]["strategy"], "flow")
        self.assertEqual(contract["relationships"]["COMMUNICATION_MEAN"]["strategy"], "connection")
        self.assertIn("flow def OperationalExchange;", ARCADIA_OA_LIBRARY_TEXT)
        self.assertIn("connection def CommunicationMean;", ARCADIA_OA_LIBRARY_TEXT)
        self.assertIn("requirement def OperationalCapability;", ARCADIA_OA_LIBRARY_TEXT)
        self.assertNotIn("OperationalProcess", ARCADIA_OA_LIBRARY_TEXT)

    def test_generator_contains_no_hardcoded_arcadia_mapping_names(self) -> None:
        source = Path(sysml_v2.__file__).read_text(encoding="utf-8")
        forbidden = [
            "OperationalCapability",
            "OperationalEntity",
            "OperationalActor",
            "OperationalActivity",
            "OperationalExchange",
            "CommunicationMean",
            "OperationalScenario",
            "OPERATIONAL_EXCHANGE",
            "COMMUNICATION_MEAN",
            "PERFORMS",
            "CONTAINS",
            "LOCATED_IN",
            "DECOMPOSES",
            "SUPPORTS_CAPABILITY",
        ]
        for token in forbidden:
            self.assertNotIn(
                token,
                source,
                msg=f"Mapping token {token} must live only in ArcadiaOA library files",
            )

    def test_generates_declared_flow_connection_perform_and_containment(self) -> None:
        text = generate_sysml_v2(sample_payload())
        self.assertIn(
            "flow oa_exchange_Threat_Information : OperationalExchange",
            text,
        )
        self.assertIn(
            "from oa_activity_Detect_Threat.oa_exchange_1_out",
            text,
        )
        self.assertIn(
            "to oa_activity_Assess_Threat.oa_exchange_1_in;",
            text,
        )
        self.assertIn(
            "connection oa_communication_Radio : CommunicationMean connect",
            text,
        )
        self.assertIn(
            "perform oa_operationalBehavior.oa_activity_Detect_Threat;",
            text,
        )
        self.assertIn("part oa_entity_Control_Center : OperationalEntity {", text)
        self.assertIn("part oa_actor_Operator : OperationalActor {", text)
        self.assertNotIn("port oa_communication_Radio", text)

    def test_supports_capability_uses_library_declared_allocation_direction(self) -> None:
        payload = sample_payload()
        payload["edges"].append(
            {
                "source": "activity:detect",
                "target": "cap:respond",
                "key": 1,
                "type": "SUPPORTS_CAPABILITY",
            }
        )
        text = generate_sysml_v2(payload)
        self.assertIn(
            "allocate oa_capability_Respond_to_threat "
            "to oa_operationalBehavior.oa_activity_Detect_Threat;",
            text,
        )
        self.assertNotIn("UNMAPPED Arcadia relation SUPPORTS_CAPABILITY", text)
        self.assertNotIn("satisfy oa_capability", text)

    def test_located_in_uses_non_composite_reference_not_containment(self) -> None:
        payload = sample_payload()
        payload["nodes"].append(
            {
                "id": "entity:building",
                "type": "OperationalEntity",
                "name": "Operations Building",
            }
        )
        payload["edges"].append(
            {
                "source": "actor:operator",
                "target": "entity:building",
                "key": 0,
                "type": "LOCATED_IN",
            }
        )
        text = generate_sysml_v2(payload)
        self.assertIn(
            "ref part oa_locatedIn_Operations_Building : OperationalEntity = "
            "oa_operationalContext.oa_entity_Operations_Building;",
            text,
        )
        self.assertNotIn("UNMAPPED Arcadia relation LOCATED_IN", text)
        # The operator remains structurally nested only under Control Center via CONTAINS.
        center_index = text.index("part oa_entity_Control_Center : OperationalEntity {")
        operator_index = text.index("part oa_actor_Operator : OperationalActor {")
        building_index = text.index("part oa_entity_Operations_Building : OperationalEntity")
        self.assertGreater(operator_index, center_index)
        self.assertGreater(building_index, operator_index)

    def test_activity_decomposition_is_native_nested_action_usage(self) -> None:
        payload = sample_payload()
        payload["nodes"].append(
            {
                "id": "activity:respond",
                "type": "OperationalActivity",
                "name": "Respond To Threat",
            }
        )
        payload["edges"].append(
            {
                "source": "activity:respond",
                "target": "activity:detect",
                "key": 0,
                "type": "DECOMPOSES",
            }
        )
        text = generate_sysml_v2(payload)
        self.assertIn("action oa_activity_Respond_To_Threat : OperationalActivity {", text)
        self.assertIn("action oa_activity_Detect_Threat : OperationalActivity {", text)
        self.assertIn(
            "from oa_activity_Respond_To_Threat.oa_activity_Detect_Threat.oa_exchange_1_out",
            text,
        )
        self.assertIn(
            "perform oa_operationalBehavior.oa_activity_Respond_To_Threat.oa_activity_Detect_Threat;",
            text,
        )
        self.assertNotIn("UNMAPPED Arcadia relation DECOMPOSES", text)

    def test_capability_decomposition_is_native_nested_requirement_usage(self) -> None:
        payload = sample_payload()
        payload["nodes"].append(
            {
                "id": "cap:protect",
                "type": "OperationalCapability",
                "name": "Protect Area",
            }
        )
        payload["edges"].append(
            {
                "source": "cap:protect",
                "target": "cap:respond",
                "key": 0,
                "type": "DECOMPOSES",
            }
        )
        text = generate_sysml_v2(payload)
        self.assertIn("requirement oa_capability_Protect_Area : OperationalCapability {", text)
        self.assertIn("requirement oa_capability_Respond_to_threat : OperationalCapability;", text)
        self.assertNotIn("UNMAPPED Arcadia relation DECOMPOSES", text)

    def test_invalid_second_decomposition_parent_is_not_invented(self) -> None:
        payload = sample_payload()
        payload["nodes"].extend(
            [
                {
                    "id": "activity:parent-a",
                    "type": "OperationalActivity",
                    "name": "Parent A",
                },
                {
                    "id": "activity:parent-b",
                    "type": "OperationalActivity",
                    "name": "Parent B",
                },
            ]
        )
        payload["edges"].extend(
            [
                {
                    "source": "activity:parent-a",
                    "target": "activity:detect",
                    "key": 0,
                    "type": "DECOMPOSES",
                },
                {
                    "source": "activity:parent-b",
                    "target": "activity:detect",
                    "key": 0,
                    "type": "DECOMPOSES",
                },
            ]
        )
        text = generate_sysml_v2(payload)
        self.assertIn("UNMAPPED Arcadia relation DECOMPOSES", text)
        self.assertEqual(text.count("action oa_activity_Detect_Threat : OperationalActivity"), 1)

    def test_removing_mapping_from_library_prevents_generation(self) -> None:
        contract = copy.deepcopy(DEFAULT_ARCADIA_OA_LIBRARY.contract)
        contract["relationships"]["OPERATIONAL_EXCHANGE"] = {"strategy": "unmapped"}
        contract["operational_scenario"] = {}
        library = validate_arcadia_oa_library(
            ArcadiaOALibrary(DEFAULT_ARCADIA_OA_LIBRARY.sysml_text, contract)
        )
        text = generate_sysml_v2(sample_payload(), library=library)
        self.assertNotIn("flow oa_exchange_Threat_Information", text)
        self.assertIn("UNMAPPED Arcadia relation OPERATIONAL_EXCHANGE", text)

    def test_unknown_source_relation_never_uses_generic_fallback(self) -> None:
        payload = sample_payload()
        payload["edges"].append(
            {
                "source": "activity:detect",
                "target": "activity:assess",
                "key": 99,
                "type": "FUTURE_RELATION",
                "name": "Must not be invented",
            }
        )
        text = generate_sysml_v2(payload)
        self.assertIn("UNMAPPED Arcadia relation FUTURE_RELATION", text)
        self.assertNotIn("connection oa_communication_Must_not_be_invented", text)
        self.assertNotIn("flow oa_exchange_Must_not_be_invented", text)

    def test_unknown_source_node_never_uses_generic_fallback(self) -> None:
        payload = sample_payload()
        payload["nodes"].append(
            {
                "id": "future:1",
                "type": "FutureConcept",
                "name": "Do Not Guess",
            }
        )
        text = generate_sysml_v2(payload)
        self.assertIn("UNMAPPED Arcadia node FutureConcept: Do Not Guess", text)
        self.assertNotIn("Do_Not_Guess", text)

    def test_scenario_mapping_comes_from_library_contract(self) -> None:
        text = generate_sysml_v2(sample_payload(), scenarios=[sample_scenario()])
        self.assertIn("action oa_scenario_Nominal_response : OperationalScenario", text)
        self.assertIn("first oa_step1_Detect_Threat;", text)
        self.assertIn("then oa_step2_Assess_Threat;", text)
        self.assertIn("flow oa_exchange_Threat_Information : OperationalExchange", text)
        self.assertIn(
            "Communication Mean reference retained without additional SysML mapping: Radio",
            text,
        )

    def test_temporary_content_is_comment_only(self) -> None:
        text = generate_sysml_v2(
            sample_payload(),
            drafts=[
                {
                    "id": "draft:1",
                    "type": "Pending",
                    "name": "Candidate participant",
                }
            ],
        )
        self.assertIn("// TEMPORARY: Candidate participant [Pending]", text)

    def test_generation_is_deterministic(self) -> None:
        first = sample_payload()
        second = sample_payload()
        second["nodes"] = list(reversed(second["nodes"]))
        second["edges"] = list(reversed(second["edges"]))
        self.assertEqual(generate_sysml_v2(first), generate_sysml_v2(second))


if __name__ == "__main__":
    unittest.main()
