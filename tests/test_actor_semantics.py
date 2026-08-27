import unittest
from unittest.mock import patch

from app import OAApp
from ontology import CONCEPT_GUIDANCE


class OperationalActorSemanticsTests(unittest.TestCase):
    def test_non_human_actor_requires_and_records_confirmation(self) -> None:
        builder = OAApp()

        with patch.object(builder, "introduce_concept"), patch.object(
            builder,
            "ask_text",
            side_effect=[
                "Autonomous Watch",
                "Non-human indivisible participant that observes the operational area.",
            ],
        ), patch.object(
            builder,
            "ask_decision",
            side_effect=["no", "yes"],
        ), patch.object(
            builder,
            "ask_limitations",
            return_value=([], []),
        ):
            node_id = builder.create_element("OperationalActor")

        self.assertTrue(node_id)
        data = builder.model.graph.nodes[node_id]
        self.assertEqual(data["actor_nature"], "NON_HUMAN")
        self.assertEqual(data["exception_confirmed_by"], "user")
        self.assertTrue(data["non_decomposable"])

    def test_rejected_non_human_exception_creates_nothing(self) -> None:
        builder = OAApp()

        with patch.object(builder, "introduce_concept"), patch.object(
            builder,
            "ask_text",
            side_effect=[
                "Autonomous Watch",
                "Non-human participant proposed for the operation.",
            ],
        ), patch.object(
            builder,
            "ask_decision",
            side_effect=["no", "no"],
        ):
            node_id = builder.create_element("OperationalActor")

        self.assertEqual(node_id, "")
        self.assertEqual(builder.model.graph.number_of_nodes(), 0)

    def test_guidance_uses_usually_human_semantics(self) -> None:
        definition = CONCEPT_GUIDANCE["OperationalActor"]["definition"]
        self.assertIn("usually", definition)
        self.assertIn("non-decomposable", definition)
        self.assertNotIn("always", definition.casefold())


if __name__ == "__main__":
    unittest.main()
