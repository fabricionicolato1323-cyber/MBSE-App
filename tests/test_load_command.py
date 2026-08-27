import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from app import OAApp
from graph_model import OAGraph


def add_entity(model: OAGraph, name: str) -> str:
    ok, node_id, error = model.add_node(
        "OperationalEntity",
        name,
        f"Operational entity represented by {name}.",
    )
    if not ok:
        raise AssertionError(error)
    return node_id


def write_legacy_model(path: Path) -> str:
    legacy = OAGraph()
    node_id = add_entity(legacy, "Operations Center")
    legacy.save(str(path))
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = 1
    del document["graph"]["nodes"][0]["sid"]
    path.write_text(json.dumps(document), encoding="utf-8")
    return node_id


class LoadCommandTests(unittest.TestCase):
    def test_load_command_applies_legacy_plan_after_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oa_model.json"
            node_id = write_legacy_model(path)
            builder = OAApp()

            with patch.object(app, "DEFAULT_SAVE_PATH", path), patch.object(
                builder,
                "ask_decision",
                return_value="yes",
            ):
                handled = builder.command("/load")

        self.assertTrue(handled)
        self.assertIn(node_id, builder.model.graph)
        self.assertEqual(builder.model.graph.nodes[node_id]["sid"], node_id)
        self.assertIn("Migrated and loaded", builder.notice)

    def test_load_command_keeps_active_graph_when_migration_is_declined(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oa_model.json"
            write_legacy_model(path)
            builder = OAApp()
            active_id = add_entity(builder.model, "Field Team")

            with patch.object(app, "DEFAULT_SAVE_PATH", path), patch.object(
                builder,
                "ask_decision",
                return_value="no",
            ):
                handled = builder.command("/load")

        self.assertTrue(handled)
        self.assertEqual(list(builder.model.graph.nodes), [active_id])
        self.assertIn("active model was not changed", builder.notice)


if __name__ == "__main__":
    unittest.main()
