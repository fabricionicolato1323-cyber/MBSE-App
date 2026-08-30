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
        self.assertEqual(
            contract["relationships"]["OPERATIONAL_EXCHANGE"]["strategy"],
            "flow",
        )
        self.assertEqual(
            contract["relationships"]["COMMUNICATION_MEAN"]["strategy"],
            "connection",
        )
        self.assertIn("flow def OperationalExchange;", ARCADIA_OA_LIBRARY_TEXT)
        self.assertIn("connection def CommunicationMean;", ARCADIA_OA_LIBRARY_TEXT)
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

    def test_generates_only_declared_flow_connection_and_perform_mappings(self) -> None:
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
        self.assertNotIn("port oa_communication_Radio", text)

    def test_removing_mapping_from_library_prevents_generation(self) -> None:
        contract = copy.deepcopy(DEFAULT_ARCADIA_OA_LIBRARY.contract)
        contract["relationships"]["OPERATIONAL_EXCHANGE"] = {
            "strategy": "unmapped"
        }
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
        self.assertNotIn(
            "connection oa_communication_Must_not_be_invented",
            text,
        )
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
        text = generate_sysml_v2(
            sample_payload(),
            scenarios=[sample_scenario()],
        )
        self.assertIn(
            "action oa_scenario_Nominal_response : OperationalScenario",
            text,
        )
        self.assertIn("first oa_step1_Detect_Threat;", text)
        self.assertIn("then oa_step2_Assess_Threat;", text)
        self.assertIn(
            "flow oa_exchange_Threat_Information : OperationalExchange",
            text,
        )
        self.assertIn(
            "Communication Mean reference retained without additional SysML mapping: Radio",
            text,
        )

    def test_declared_unmapped_relations_are_comments_only(self) -> None:
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
            "UNMAPPED Arcadia relation SUPPORTS_CAPABILITY: "
            "Detect Threat -> Respond to threat",
            text,
        )
        self.assertNotIn("satisfy oa_capability", text)

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
