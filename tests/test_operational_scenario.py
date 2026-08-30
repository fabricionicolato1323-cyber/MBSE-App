from __future__ import annotations

import unittest

from operational_scenario import (
    ScenarioError,
    create_scenario_record,
    merge_scenarios_into_payload,
    scenario_snapshots,
    scenarios_from_payload,
)


def sample_payload() -> dict:
    return {
        "directed": True,
        "multigraph": True,
        "graph": {"model": "Arcadia Operational Analysis"},
        "nodes": [
            {"id": "activity:a", "type": "OperationalActivity", "name": "Activity A"},
            {"id": "activity:b", "type": "OperationalActivity", "name": "Activity B"},
            {"id": "activity:c", "type": "OperationalActivity", "name": "Activity C"},
            {"id": "actor:a", "type": "OperationalActor", "name": "Actor A"},
            {"id": "actor:b", "type": "OperationalActor", "name": "Actor B"},
        ],
        "edges": [
            {
                "source": "activity:a",
                "target": "activity:b",
                "key": 0,
                "type": "OPERATIONAL_EXCHANGE",
                "name": "Exchange AB",
            },
            {
                "source": "activity:b",
                "target": "activity:c",
                "key": 0,
                "type": "OPERATIONAL_EXCHANGE",
                "name": "Exchange BC",
            },
            {
                "source": "actor:a",
                "target": "actor:b",
                "key": 0,
                "type": "COMMUNICATION_MEAN",
                "name": "Radio",
            },
        ],
    }


class OperationalScenarioTests(unittest.TestCase):
    def test_create_scenario_preserves_order_and_references(self) -> None:
        payload = sample_payload()
        scenario = create_scenario_record(
            payload,
            [],
            name="Nominal flow",
            steps=[
                {"kind": "activity", "activity_id": "activity:a"},
                {
                    "kind": "interaction",
                    "source_activity_id": "activity:a",
                    "target_activity_id": "activity:b",
                    "edge_key": 0,
                    "exchange_name": "Exchange AB",
                    "communication_mean": {
                        "source_participant_id": "actor:a",
                        "target_participant_id": "actor:b",
                        "edge_key": 0,
                        "name": "Radio",
                    },
                },
                {"kind": "activity", "activity_id": "activity:b"},
                {
                    "kind": "interaction",
                    "source_activity_id": "activity:b",
                    "target_activity_id": "activity:c",
                    "edge_key": 0,
                    "exchange_name": "Exchange BC",
                },
                {"kind": "activity", "activity_id": "activity:c"},
            ],
        )

        self.assertEqual(scenario["id"], "OperationalScenario:nominal-flow")
        self.assertEqual([step["order"] for step in scenario["steps"]], [1, 2, 3, 4, 5])
        self.assertEqual(scenario["steps"][1]["target_activity_id"], "activity:b")
        self.assertEqual(
            scenario["steps"][1]["communication_mean"]["name"],
            "Radio",
        )

    def test_rejects_disconnected_interaction(self) -> None:
        payload = sample_payload()
        with self.assertRaises(ScenarioError):
            create_scenario_record(
                payload,
                [],
                name="Invalid",
                steps=[
                    {"kind": "activity", "activity_id": "activity:a"},
                    {
                        "kind": "interaction",
                        "source_activity_id": "activity:a",
                        "target_activity_id": "activity:c",
                        "edge_key": 0,
                        "exchange_name": "Missing",
                    },
                    {"kind": "activity", "activity_id": "activity:c"},
                ],
            )

    def test_rejects_duplicate_scenario_name(self) -> None:
        payload = sample_payload()
        existing = [
            {
                "id": "OperationalScenario:nominal-flow",
                "name": "Nominal flow",
                "steps": [],
            }
        ]
        with self.assertRaises(ScenarioError):
            create_scenario_record(
                payload,
                existing,
                name="  NOMINAL   FLOW ",
                steps=[],
            )

    def test_loaded_broken_scenario_is_marked_invalid(self) -> None:
        payload = sample_payload()
        scenario = {
            "id": "OperationalScenario:broken",
            "name": "Broken",
            "steps": [
                {"order": 1, "kind": "activity", "activity_id": "activity:a"},
                {
                    "order": 2,
                    "kind": "interaction",
                    "source_activity_id": "activity:a",
                    "target_activity_id": "activity:missing",
                    "edge_key": 0,
                    "exchange_name": "Missing",
                },
                {"order": 3, "kind": "activity", "activity_id": "activity:missing"},
            ],
        }

        snapshot = scenario_snapshots(payload, [scenario])[0]
        self.assertFalse(snapshot["valid"])
        self.assertTrue(snapshot["issues"])

    def test_export_metadata_roundtrip(self) -> None:
        payload = sample_payload()
        scenario = {
            "id": "OperationalScenario:nominal",
            "name": "Nominal",
            "steps": [],
        }
        merged = merge_scenarios_into_payload(payload, [scenario])
        self.assertEqual(scenarios_from_payload(merged), [scenario])
        self.assertNotIn("operational_scenarios", payload["graph"])


if __name__ == "__main__":
    unittest.main()
