from __future__ import annotations

import unittest

from sysml_v2 import ARCADIA_OA_LIBRARY_TEXT, generate_sysml_v2


def sample_payload() -> dict:
    return {
        "directed": True,
        "multigraph": True,
        "graph": {"model": "Arcadia Operational Analysis", "model_name": "Threat response OA"},
        "nodes": [
            {"id": "cap:respond", "type": "OperationalCapability", "name": "Respond to threat"},
            {"id": "entity:center", "type": "OperationalEntity", "name": "Control Center"},
            {"id": "actor:operator", "type": "OperationalActor", "name": "Operator"},
            {"id": "activity:detect", "type": "OperationalActivity", "name": "Detect Threat",
             "characteristics": [{"name": "Latency", "value_type": "number", "value": 2.5, "unit": "s"}]},
            {"id": "activity:assess", "type": "OperationalActivity", "name": "Assess Threat"},
        ],
        "edges": [
            {"source": "entity:center", "target": "actor:operator", "key": 0, "type": "CONTAINS"},
            {"source": "actor:operator", "target": "activity:detect", "key": 0, "type": "PERFORMS"},
            {"source": "entity:center", "target": "activity:assess", "key": 0, "type": "PERFORMS"},
            {"source": "activity:detect", "target": "activity:assess", "key": 0,
             "type": "OPERATIONAL_EXCHANGE", "name": "Threat Information"},
            {"source": "actor:operator", "target": "entity:center", "key": 0,
             "type": "COMMUNICATION_MEAN", "name": "Radio"},
        ],
    }


def sample_scenario() -> dict:
    return {
        "id": "OperationalScenario:nominal",
        "name": "Nominal response",
        "valid": True,
        "issues": [],
        "steps": [
            {"order": 1, "kind": "activity", "activity_id": "activity:detect"},
            {"order": 2, "kind": "interaction", "source_activity_id": "activity:detect",
             "target_activity_id": "activity:assess", "edge_key": 0,
             "exchange_name": "Threat Information",
             "communication_mean": {"source_participant_id": "actor:operator",
                                    "target_participant_id": "entity:center", "edge_key": 0,
                                    "name": "Radio"}},
            {"order": 3, "kind": "activity", "activity_id": "activity:assess"},
        ],
    }


class SysMLV2GenerationTests(unittest.TestCase):
    def test_library_mapping_is_frozen(self) -> None:
        self.assertIn("flow def OperationalExchange;", ARCADIA_OA_LIBRARY_TEXT)
        self.assertIn("connection def CommunicationMean;", ARCADIA_OA_LIBRARY_TEXT)
        self.assertNotIn("connection def OperationalExchange", ARCADIA_OA_LIBRARY_TEXT)
        self.assertNotIn("port def CommunicationMean", ARCADIA_OA_LIBRARY_TEXT)
        self.assertNotIn("OperationalProcess", ARCADIA_OA_LIBRARY_TEXT)

    def test_generates_flow_connection_and_perform(self) -> None:
        text = generate_sysml_v2(sample_payload())
        self.assertIn("flow oa_exchange_Threat_Information : OperationalExchange", text)
        self.assertIn("from oa_activity_Detect_Threat.oa_exchange_1_out", text)
        self.assertIn("to oa_activity_Assess_Threat.oa_exchange_1_in;", text)
        self.assertIn("connection oa_communication_Radio : CommunicationMean connect", text)
        self.assertIn("perform oa_operationalBehavior.oa_activity_Detect_Threat;", text)
        self.assertNotIn("port oa_communication_Radio", text)

    def test_scenario_preserves_order_and_exchange(self) -> None:
        text = generate_sysml_v2(sample_payload(), scenarios=[sample_scenario()])
        self.assertIn("action oa_scenario_Nominal_response : OperationalScenario", text)
        self.assertIn("first oa_step1_Detect_Threat;", text)
        self.assertIn("then oa_step2_Assess_Threat;", text)
        self.assertIn("flow oa_scenario_exchange_Threat_Information : OperationalExchange", text)
        self.assertIn("Communication Mean for this scenario exchange: Radio", text)

    def test_unfrozen_relations_are_comments(self) -> None:
        payload = sample_payload()
        payload["edges"].append({"source": "activity:detect", "target": "cap:respond", "key": 1,
                                 "type": "SUPPORTS_CAPABILITY"})
        text = generate_sysml_v2(payload)
        self.assertIn("// SUPPORTS_CAPABILITY: Detect Threat -> Respond to threat", text)
        self.assertNotIn("satisfy oa_capability", text)

    def test_temporary_content_is_not_persisted_as_sysml_usage(self) -> None:
        text = generate_sysml_v2(sample_payload(), drafts=[{"id": "draft:1", "type": "Pending",
                                                           "name": "Candidate participant"}])
        self.assertIn("// TEMPORARY: Candidate participant [Pending]", text)

    def test_generation_is_deterministic(self) -> None:
        first = sample_payload()
        second = sample_payload()
        second["nodes"] = list(reversed(second["nodes"]))
        second["edges"] = list(reversed(second["edges"]))
        self.assertEqual(generate_sysml_v2(first), generate_sysml_v2(second))


if __name__ == "__main__":
    unittest.main()
