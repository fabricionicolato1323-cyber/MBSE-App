import json
import tempfile
import unittest
from pathlib import Path

from graph_model import (
    MigrationConfirmationRequired,
    ModelLoadError,
    OAGraph,
)


def add(
    model: OAGraph,
    concept: str,
    name: str,
    description: str,
) -> str:
    ok, node_id, error = model.add_node(concept, name, description)
    if not ok:
        raise AssertionError(error)
    return node_id


class AtomicActionTests(unittest.TestCase):
    def test_compound_action_has_one_undo_boundary(self) -> None:
        model = OAGraph()

        with model.user_action():
            parent = add(
                model,
                "OperationalEntity",
                "Operations Center",
                "Organization that coordinates the operation.",
            )
            child = add(
                model,
                "OperationalEntity",
                "Field Team",
                "Operational group working in the field.",
            )
            ok, error = model.add_relation(parent, "CONTAINS", child)
            self.assertTrue(ok, error)

        self.assertEqual(model.graph.number_of_nodes(), 2)
        self.assertEqual(model.graph.number_of_edges(), 1)
        self.assertTrue(model.undo())
        self.assertEqual(model.graph.number_of_nodes(), 0)
        self.assertEqual(model.graph.number_of_edges(), 0)
        self.assertFalse(model.undo())

    def test_exception_rolls_back_complete_action(self) -> None:
        model = OAGraph()

        with self.assertRaisesRegex(RuntimeError, "stop action"):
            with model.user_action():
                add(
                    model,
                    "OperationalEntity",
                    "Operations Center",
                    "Organization that coordinates the operation.",
                )
                raise RuntimeError("stop action")

        self.assertEqual(model.graph.number_of_nodes(), 0)
        self.assertFalse(model.undo())


class AtomicLoadTests(unittest.TestCase):
    def test_valid_current_model_preserves_canonical_identity(self) -> None:
        source_model = OAGraph()
        node_id = add(
            source_model,
            "OperationalCapability",
            "Maintain safe operations",
            "Keep operations within the agreed safety boundary.",
        )

        with tempfile.TemporaryDirectory() as directory:
            path = source_model.save(str(Path(directory) / "model.json"))
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["graph"]["nodes"][0]["nodeKey"], node_id)
            self.assertEqual(document["graph"]["nodes"][0]["id"], node_id)

            loaded = OAGraph()
            loaded.load(str(path))

        self.assertIn(node_id, loaded.graph)
        self.assertEqual(loaded.graph.nodes[node_id]["id"], node_id)
        self.assertEqual(loaded.graph.nodes[node_id]["sid"], node_id)

    def test_invalid_candidate_leaves_active_graph_unchanged(self) -> None:
        active = OAGraph()
        active_id = add(
            active,
            "OperationalCapability",
            "Maintain safe operations",
            "Keep operations within the agreed safety boundary.",
        )
        candidate = OAGraph()
        add(
            candidate,
            "OperationalEntity",
            "Operations Center",
            "Organization that coordinates the operation.",
        )

        with tempfile.TemporaryDirectory() as directory:
            path = candidate.save(str(Path(directory) / "invalid.json"))
            document = json.loads(path.read_text(encoding="utf-8"))
            document["graph"]["nodes"][0]["description"] = ""
            path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ModelLoadError, "no core description"):
                active.load(str(path))

        self.assertEqual(list(active.graph.nodes), [active_id])
        self.assertEqual(active.name(active_id), "Maintain safe operations")

    def test_schema_one_requires_confirmation_and_repairs_missing_sid(self) -> None:
        legacy = OAGraph()
        node_id = add(
            legacy,
            "OperationalEntity",
            "Operations Center",
            "Organization that coordinates the operation.",
        )

        with tempfile.TemporaryDirectory() as directory:
            path = legacy.save(str(Path(directory) / "legacy.json"))
            document = json.loads(path.read_text(encoding="utf-8"))
            document["schema_version"] = 1
            del document["graph"]["nodes"][0]["sid"]
            path.write_text(json.dumps(document), encoding="utf-8")

            loaded = OAGraph()
            with self.assertRaises(MigrationConfirmationRequired) as caught:
                loaded.load(str(path))

            plan = caught.exception.plan
            self.assertTrue(plan.requires_confirmation)
            self.assertTrue(any("Missing sid" in line for line in plan.migration_summary))
            self.assertEqual(loaded.graph.number_of_nodes(), 0)

            loaded.apply_load(plan)
            source_after_load = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(loaded.graph.nodes[node_id]["sid"], node_id)
        self.assertNotIn("sid", source_after_load["graph"]["nodes"][0])

    def test_duplicate_legacy_sid_rejects_migration(self) -> None:
        legacy = OAGraph()
        add(
            legacy,
            "OperationalEntity",
            "Operations Center",
            "Organization that coordinates the operation.",
        )
        add(
            legacy,
            "OperationalEntity",
            "Field Team",
            "Operational group working in the field.",
        )

        with tempfile.TemporaryDirectory() as directory:
            path = legacy.save(str(Path(directory) / "legacy.json"))
            document = json.loads(path.read_text(encoding="utf-8"))
            document["schema_version"] = 1
            for node in document["graph"]["nodes"]:
                node["sid"] = "duplicate-external-alias"
            path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ModelLoadError, "Duplicate sid"):
                OAGraph().load(str(path))


if __name__ == "__main__":
    unittest.main()
