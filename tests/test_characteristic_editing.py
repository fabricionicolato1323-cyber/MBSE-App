import unittest
from unittest.mock import patch

from app import OAApp, RetryCharacteristic
from app_extensions import looks_like_plural_human_label
from graph_model import OAGraph


def characteristic(name="Duration", lower="5", upper="10"):
    parameter = {
        "id": "parameter-1",
        "name": name,
        "description": "Operational duration.",
        "quantityKind": "duration",
        "valueType": "Real",
        "unit": "minutes",
    }
    constraint = {
        "id": "constraint-1",
        "name": f"Range {name}",
        "description": f"Range operational limitation for {name}.",
        "parameterId": "parameter-1",
        "operator": "RANGE",
        "lowerValue": lower,
        "upperValue": upper,
        "applicableCondition": "Normal operation",
        "scope": "LOCAL",
        "aggregation": "",
        "customAggregation": "",
    }
    return parameter, constraint


def add_action(model):
    parameter, constraint = characteristic()
    ok, node_id, error = model.add_node(
        "OperationalActivity",
        "Transport passengers",
        "Move passengers between the required locations.",
        parameters=[parameter],
        constraints=[constraint],
    )
    if not ok:
        raise AssertionError(error)
    return node_id


class CharacteristicWriteBarrierTests(unittest.TestCase):
    def test_duplicate_names_are_rejected_case_insensitively(self):
        first, first_constraint = characteristic("Duration")
        second, second_constraint = characteristic("duration")
        second["id"] = "parameter-2"
        second_constraint["id"] = "constraint-2"
        second_constraint["parameterId"] = "parameter-2"
        ok, _, error = OAGraph().add_node(
            "OperationalActivity",
            "Transport passengers",
            "Move passengers between the required locations.",
            parameters=[first, second],
            constraints=[first_constraint, second_constraint],
        )
        self.assertFalse(ok)
        self.assertIn("unique", error)

    def test_edit_preserves_parameter_and_constraint_ids_and_is_undoable(self):
        model = OAGraph()
        node_id = add_action(model)
        model._history.clear()
        parameter, constraint = model.get_characteristic(node_id, "parameter-1")
        constraint["upperValue"] = "15"

        ok, error = model.replace_characteristic(
            node_id, "parameter-1", parameter, constraint
        )
        self.assertTrue(ok, error)
        edited_parameter, edited_constraint = model.get_characteristic(
            node_id, "parameter-1"
        )
        self.assertEqual(edited_parameter["id"], "parameter-1")
        self.assertEqual(edited_constraint["id"], "constraint-1")
        self.assertEqual(edited_constraint["upperValue"], "15")
        self.assertTrue(model.undo())
        _, restored_constraint = model.get_characteristic(node_id, "parameter-1")
        self.assertEqual(restored_constraint["upperValue"], "10")

    def test_remove_only_selected_characteristic(self):
        model = OAGraph()
        node_id = add_action(model)
        second, second_constraint = characteristic("Maximum capacity", "1", "40")
        second["id"] = "parameter-2"
        second["quantityKind"] = "count"
        second["unit"] = "people"
        second_constraint["id"] = "constraint-2"
        second_constraint["parameterId"] = "parameter-2"
        data = model.graph.nodes[node_id]
        self.assertTrue(model.update_node(
            node_id,
            parameters=list(data["parameters"]) + [second],
            constraints=list(data["constraints"]) + [second_constraint],
        )[0])
        model._history.clear()

        ok, error = model.remove_characteristic(node_id, "parameter-1")
        self.assertTrue(ok, error)
        self.assertFalse(model.characteristic_name_exists(node_id, "Duration"))
        self.assertTrue(model.characteristic_name_exists(node_id, "Maximum capacity"))


class GuidedUxTests(unittest.TestCase):
    def test_plural_human_warning_is_conservative(self):
        self.assertTrue(looks_like_plural_human_label("Passengers"))
        self.assertTrue(looks_like_plural_human_label("Field soldiers"))
        self.assertFalse(looks_like_plural_human_label("Driver"))
        self.assertFalse(looks_like_plural_human_label("Operations"))

    def test_plural_actor_can_be_redirected_to_collective_category(self):
        app = OAApp()
        with patch.object(app, "introduce_concept"), patch.object(
            app,
            "ask_text",
            side_effect=["Passengers", "People transported during the operation."],
        ), patch.object(
            app,
            "ask_choice",
            return_value="OperationalEntity",
        ), patch.object(
            app,
            "ask_limitations",
            return_value=([], []),
        ):
            node_id = app.create_element("OperationalActor")
        self.assertTrue(node_id)
        self.assertEqual(app.model.graph.nodes[node_id]["type"], "OperationalEntity")

    def test_duplicate_is_detected_immediately_after_name(self):
        app = OAApp()
        app._characteristic_existing_names = {"duration"}
        with patch.object(app, "ask_text", return_value="Duration") as ask_text:
            with self.assertRaises(RetryCharacteristic):
                app._collect_limitation("OperationalActivity")
        self.assertEqual(ask_text.call_count, 1)
        self.assertIn("already exists", app.notice)

    def test_check_distinguishes_persisted_model_from_current_draft(self):
        app = OAApp()
        app._characteristic_draft_active = True
        app._current_characteristic_draft_name = "Duration"
        with patch.object(app, "show_page") as show_page:
            self.assertTrue(app.command("/check"))
        body = show_page.call_args.args[1]
        self.assertIn("Persisted model", body)
        self.assertIn("Current draft", body)
        self.assertIn("Duration", body)
        self.assertIn("has not been written", body)


if __name__ == "__main__":
    unittest.main()
