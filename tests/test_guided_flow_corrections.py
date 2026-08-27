import unittest
from unittest.mock import patch

from app import OAApp
from graph_model import OAGraph


def add(model: OAGraph, concept: str, name: str, description: str, **attributes) -> str:
    ok, node_id, error = model.add_node(concept, name, description, **attributes)
    if not ok:
        raise AssertionError(error)
    return node_id


def characteristic(
    *,
    quantity_kind: str = "length",
    unit: str = "km",
    operator: str = "MAX",
    value: str = "5",
    lower: str = "",
    upper: str = "",
    aggregation: str = "",
    custom_aggregation: str = "",
) -> tuple[list[dict], list[dict]]:
    parameter_id = "parameter-1"
    parameter = {
        "id": parameter_id,
        "name": "detection radius",
        "description": "Maximum distance at which a drone can be detected.",
        "quantityKind": quantity_kind,
        "valueType": "Real",
        "unit": unit,
    }
    constraint = {
        "id": "constraint-1",
        "name": f"{operator.title()} detection radius",
        "description": "Operational detection limitation.",
        "parameterId": parameter_id,
        "operator": operator,
        "scope": "HIERARCHY" if aggregation else "LOCAL",
        "aggregation": aggregation,
        "customAggregation": custom_aggregation,
        "applicableCondition": "Normal operation",
        "rationale": "Customer safety objective",
    }
    if operator == "RANGE":
        constraint.update({"lowerValue": lower, "upperValue": upper})
    else:
        constraint["value"] = value
    return [parameter], [constraint]


class UndoFeedbackTests(unittest.TestCase):
    def test_relationship_undo_identifies_the_removed_action(self) -> None:
        model = OAGraph()
        actor = add(
            model,
            "OperationalActor",
            "Field Soldier",
            "Human role operating the countermeasure equipment.",
        )
        capability = add(
            model,
            "OperationalCapability",
            "Keep protected area safe",
            "Protect people and infrastructure from hostile drones.",
        )
        model._history.clear()
        self.assertTrue(model.add_relation(actor, "INVOLVED_IN_CAPABILITY", capability)[0])

        self.assertTrue(model.undo())

        self.assertFalse(model.has_relation(actor, "INVOLVED_IN_CAPABILITY", capability))
        self.assertEqual(
            model.last_undo_description,
            "added relationship Field Soldier --INVOLVED_IN_CAPABILITY--> Keep protected area safe",
        )

    def test_back_during_attribute_entry_explains_that_the_draft_was_not_changed(self) -> None:
        app = OAApp()
        actor = add(
            app.model,
            "OperationalActor",
            "Field Soldier",
            "Human role operating the countermeasure equipment.",
        )
        capability = add(
            app.model,
            "OperationalCapability",
            "Keep protected area safe",
            "Protect people and infrastructure from hostile drones.",
        )
        app.model._history.clear()
        self.assertTrue(
            app.model.add_relation(actor, "INVOLVED_IN_CAPABILITY", capability)[0]
        )
        app._characteristic_draft_active = True

        self.assertTrue(app.command("/back"))

        self.assertIn("INVOLVED_IN_CAPABILITY", app.notice)
        self.assertIn("Current attribute draft was not changed", app.notice)
        self.assertIn("/retry", app.notice)


class CharacteristicValidationTests(unittest.TestCase):
    def test_nonnumeric_constraint_is_rejected(self) -> None:
        parameters, constraints = characteristic(value="five")
        ok, _, error = OAGraph().add_node(
            "OperationalCapability",
            "Maintain protected operations",
            "Keep the operation inside its protection boundary.",
            parameters=parameters,
            constraints=constraints,
        )
        self.assertFalse(ok)
        self.assertIn("finite numbers", error)

    def test_inverted_range_is_rejected(self) -> None:
        parameters, constraints = characteristic(operator="RANGE", lower="10", upper="5")
        ok, _, error = OAGraph().add_node(
            "OperationalCapability",
            "Maintain protected operations",
            "Keep the operation inside its protection boundary.",
            parameters=parameters,
            constraints=constraints,
        )
        self.assertFalse(ok)
        self.assertIn("lower value", error)

    def test_placeholder_custom_aggregation_is_rejected(self) -> None:
        parameters, constraints = characteristic(
            aggregation="CUSTOM",
            custom_aggregation="lll",
        )
        ok, _, error = OAGraph().add_node(
            "OperationalCapability",
            "Maintain protected operations",
            "Keep the operation inside its protection boundary.",
            parameters=parameters,
            constraints=constraints,
        )
        self.assertFalse(ok)
        self.assertIn("explicit rule", error)

    def test_quantity_kind_unit_mismatch_is_non_blocking(self) -> None:
        parameters, constraints = characteristic(quantity_kind="area", unit="km")
        model = OAGraph()

        warnings = model.characteristic_warnings(parameters, constraints)
        ok, _, error = model.add_node(
            "OperationalCapability",
            "Maintain protected operations",
            "Keep the operation inside its protection boundary.",
            parameters=parameters,
            constraints=constraints,
        )

        self.assertTrue(ok, error)
        self.assertTrue(any("may not match" in warning for warning in warnings))

    def test_measurement_term_suggests_a_dimensional_kind(self) -> None:
        parameters, constraints = characteristic(quantity_kind="radius", unit="km")
        warnings = OAGraph.characteristic_warnings(parameters, constraints)
        self.assertTrue(any("use 'length'" in warning for warning in warnings))


class GuidedCorrectionTests(unittest.TestCase):
    def test_retry_restarts_only_the_current_characteristic(self) -> None:
        app = OAApp()
        answers = iter([
            "1",  # add a limitation
            "are",  # mistaken measurement name
            "/retry",  # restart while entering its description
            "detection radius",
            "Maximum distance at which a drone can be detected.",
            "length",
            "km",
            "2",  # MAX
            "10",
            "not now",
            "not now",
            "1",  # LOCAL
            "2",  # no additional limitation
        ])

        with patch("builtins.input", side_effect=lambda _="": next(answers)), patch.object(
            app,
            "draw_question",
        ):
            parameters, constraints = app.ask_limitations(
                "OperationalCapability",
                "Keep protected area safe",
            )

        self.assertEqual(len(parameters), 1)
        self.assertEqual(parameters[0]["name"], "detection radius")
        self.assertEqual(constraints[0]["value"], "10")
        self.assertIn("discarded", app.notice)

    def test_system_of_interest_candidate_is_not_added_without_external_confirmation(self) -> None:
        app = OAApp()
        with patch.object(app, "introduce_concept"), patch.object(
            app,
            "ask_text",
            side_effect=["Drone detection system", "System that detects incoming drones."],
        ), patch.object(app, "ask_choice", return_value="no"):
            node_id = app.create_element("OperationalEntity")

        self.assertEqual(node_id, "")
        self.assertEqual(app.model.graph.number_of_nodes(), 0)
        self.assertIn("creation cancelled", app.notice)

    def test_confirmed_external_system_is_preserved_as_user_confirmed(self) -> None:
        app = OAApp()
        with patch.object(app, "introduce_concept"), patch.object(
            app,
            "ask_text",
            side_effect=["Drone detection system", "Existing external system that reports drones."],
        ), patch.object(app, "ask_choice", return_value="yes"), patch.object(
            app,
            "ask_limitations",
            return_value=([], []),
        ):
            node_id = app.create_element("OperationalEntity")

        self.assertTrue(node_id)
        self.assertEqual(
            app.model.graph.nodes[node_id]["external_system_confirmed_by"],
            "user",
        )


class ModelReviewTests(unittest.TestCase):
    def test_review_uses_correct_plurals_and_shows_characteristic_values(self) -> None:
        parameters, constraints = characteristic()
        model = OAGraph()
        add(
            model,
            "OperationalCapability",
            "Keep protected area safe",
            "Protect people and infrastructure from hostile drones.",
            parameters=parameters,
            constraints=constraints,
            summary="Protect the designated operating area.",
            status="REVIEWED",
            review="Numeric target reviewed with the customer.",
        )

        output = model.friendly_show()

        self.assertTrue(output.startswith("Operational Capabilities"))
        self.assertNotIn("MODEL SO FAR", output)
        self.assertNotIn("Capabilitys", output)
        self.assertIn("Operational Entities", output)
        self.assertIn("Operational Activities", output)
        capability_id = model.nodes_of_type("OperationalCapability")[0]
        self.assertIn(f"ID: {capability_id}", output)
        self.assertIn("Type: OperationalCapability", output)
        self.assertIn("Capella type: OperationalCapability", output)
        self.assertIn("Status: REVIEWED", output)
        self.assertIn("Summary: Protect the designated operating area.", output)
        self.assertIn("Review: Numeric target reviewed with the customer.", output)
        self.assertIn("Attribute: detection radius", output)
        self.assertIn("Maximum: 5 km", output)
        self.assertIn("Condition: Normal operation", output)
        self.assertIn("Rationale/source: Customer safety objective", output)

    def test_review_shows_range_values_and_complete_relationships(self) -> None:
        parameters, constraints = characteristic(
            operator="RANGE",
            lower="2.5",
            upper="10",
        )
        model = OAGraph()
        capability = add(
            model,
            "OperationalCapability",
            "Keep protected area safe",
            "Protect people and infrastructure from hostile drones.",
            parameters=parameters,
            constraints=constraints,
        )
        actor = add(
            model,
            "OperationalActor",
            "Field Soldier",
            "Human role operating the countermeasure equipment.",
            actor_nature="HUMAN",
        )
        self.assertTrue(
            model.add_relation(actor, "INVOLVED_IN_CAPABILITY", capability)[0]
        )

        output = model.friendly_show()

        self.assertIn("Range: 2.5 to 10 km", output)
        self.assertIn("Actor nature: HUMAN", output)
        self.assertIn(f"Field Soldier [{actor}] --INVOLVED_IN_CAPABILITY-->", output)
        self.assertIn(f"Keep protected area safe [{capability}]", output)
        self.assertIn("Attributes/limitations: none", output)


if __name__ == "__main__":
    unittest.main()
