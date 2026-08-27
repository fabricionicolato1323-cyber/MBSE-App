import unittest
from unittest.mock import patch

from app import OAApp


def add(builder: OAApp, concept: str, name: str, description: str) -> str:
    ok, node_id, error = builder.model.add_node(concept, name, description)
    if not ok:
        raise AssertionError(error)
    return node_id


class AtomicApplicationActionTests(unittest.TestCase):
    def test_endpoint_replacement_is_undone_as_one_action(self) -> None:
        builder = OAApp()
        exchange = add(
            builder,
            "OperationalExchange",
            "Authorization data",
            "Authorization information transferred between activities.",
        )
        old_activity = add(
            builder,
            "OperationalActivity",
            "Verify authorization data",
            "Confirm that authorization data is valid.",
        )
        new_activity = add(
            builder,
            "OperationalActivity",
            "Receive authorization data",
            "Receive authorization data for operational use.",
        )
        ok, error = builder.model.add_relation(exchange, "SOURCE_ACTIVITY", old_activity)
        self.assertTrue(ok, error)
        builder.model._history.clear()

        with patch.object(builder, "select_node", return_value=new_activity), patch.object(
            builder,
            "introduce_relation",
        ):
            builder.replace_endpoint(
                exchange,
                "SOURCE_ACTIVITY",
                [old_activity, new_activity],
            )

        self.assertEqual(
            builder.model.relation_targets(exchange, "SOURCE_ACTIVITY"),
            [new_activity],
        )
        self.assertTrue(builder.model.undo())
        self.assertEqual(
            builder.model.relation_targets(exchange, "SOURCE_ACTIVITY"),
            [old_activity],
        )
        self.assertFalse(builder.model.undo())

    def test_relationship_move_is_undone_as_one_action(self) -> None:
        builder = OAApp()
        parent = add(
            builder,
            "OperationalEntity",
            "Operations Center",
            "Organization that coordinates the operation.",
        )
        child = add(
            builder,
            "OperationalEntity",
            "Field Team",
            "Operational group working in the field.",
        )
        activity = add(
            builder,
            "OperationalActivity",
            "Coordinate field operations",
            "Coordinate operational work performed in the field.",
        )
        self.assertTrue(builder.model.add_relation(parent, "CONTAINS", child)[0])
        self.assertTrue(builder.model.add_relation(parent, "PERFORMS", activity)[0])
        builder.model._history.clear()

        with patch.object(builder, "ask_choice", return_value="child"):
            builder.allocate_parent_links(parent, child, "CONTAINS")

        self.assertFalse(builder.model.has_relation(parent, "PERFORMS", activity))
        self.assertTrue(builder.model.has_relation(child, "PERFORMS", activity))
        self.assertTrue(builder.model.undo())
        self.assertTrue(builder.model.has_relation(parent, "PERFORMS", activity))
        self.assertFalse(builder.model.has_relation(child, "PERFORMS", activity))
        self.assertFalse(builder.model.undo())


if __name__ == "__main__":
    unittest.main()
