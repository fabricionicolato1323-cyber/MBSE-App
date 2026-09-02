from __future__ import annotations

import unittest


class PySAMLevel1BAPIContractTests(unittest.TestCase):
    def test_pysam_factory_exposes_level1b_creation_methods(self) -> None:
        from ansys.sam.sysml2.tools import Factory

        required = {
            "create_package",
            "create_library_package",
            "create_part_definition",
            "create_action_definition",
            "create_item_definition",
            "create_flow_connection_definition",
            "create_connection_definition",
            "create_requirement_definition",
            "create_subclassification",
            "create_part_usage",
            "create_action_usage",
            "create_requirement_usage",
            "create_attribute_usage",
            "create_documentation",
            "create_perform_action_usage",
            "create_flow_connection_usage",
            "create_connection_usage",
            "create_allocation_usage",
            "create_satisfy_requirement_usage",
            "create_reference_usage",
            "create_reference_subsetting",
            "create_succession",
            "create_textual_representation",
        }
        missing = sorted(name for name in required if not hasattr(Factory, name))
        self.assertEqual(missing, [], f"PySAM 0.3.1 Factory is missing: {missing}")


if __name__ == "__main__":
    unittest.main()
