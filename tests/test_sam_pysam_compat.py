from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sam_pysam_compat import install_transactional_factory_fix


class PySamTransactionalCompatibilityTests(unittest.TestCase):
    def test_transaction_factory_and_observer_are_fixed_or_upstream_fixed(self) -> None:
        result = install_transactional_factory_fix()
        self.assertIn("required", result)
        self.assertIn("applied", result)
        self.assertIn("factory", result)
        self.assertIn("observer", result)

        from ansys.sam.sysml2.observer.observer import ModificationObserver
        from ansys.sam.sysml2.tools import Factory

        factory_result = result["factory"]
        factory_method = Factory._create_local_element_and_stack
        if factory_result["required"]:
            self.assertTrue(factory_result["applied"])
            self.assertTrue(
                getattr(factory_method, "_mbse_level1_transaction_fix", False)
            )
        else:
            # A future released PySAM may already contain the local storage fix.
            self.assertFalse(factory_result["applied"])

        observer_result = result["observer"]
        observer_method = ModificationObserver._commit_stack
        if observer_result["required"]:
            self.assertTrue(observer_result["applied"])
            self.assertTrue(
                getattr(observer_method, "_mbse_level1_transaction_field_fix", False)
            )
        else:
            # A future released PySAM may already canonicalize transaction fields.
            self.assertFalse(observer_result["applied"])

    def test_transaction_payload_uses_canonical_sysml_field_names(self) -> None:
        install_transactional_factory_fix()

        from ansys.sam.sysml2.classes.sysml_element import SysMLElement
        from ansys.sam.sysml2.observer.observer import ModificationObserver
        from ansys.sam.sysml2.tools import Factory

        class RecordingConnector:
            def __init__(self) -> None:
                self.commits: list[dict] = []

            def create_commit(self, project_id: str, payload: str) -> None:
                self.commits.append(json.loads(payload))

        class FakeScriptingProject:
            def __init__(self) -> None:
                self._id = "project-1"
                self._root = None
                self._env: dict[str, object] = {}

            def get_root_package(self):
                return self._root

            def add_element(self, element) -> None:
                self._env[element._id] = element

        class Root:
            def __init__(self, observer) -> None:
                self._observer = observer

        connector = RecordingConnector()
        project = FakeScriptingProject()
        observer = ModificationObserver(project, connector)
        project._root = Root(observer)
        observer.set_transactional_mode(True)
        factory = Factory(project, connector)

        owner = SysMLElement("owner-1")
        definition = SysMLElement("definition-1")

        factory.create_action_usage(
            name="1. Assess crossing condition",
            owner=owner,
            action_definition=[definition],
        )
        factory.create_flow_connection_usage(
            name="Crossing status",
            owner=owner,
            flow_connection_definition=[definition],
            source=[owner],
            target=[owner],
        )

        with patch.object(observer, "reload_project", return_value=None):
            observer._commit_stack()

        self.assertEqual(len(connector.commits), 1)
        changes = [
            item.get("payload", {}) for item in connector.commits[0].get("change", [])
        ]
        action_payload = next(
            item for item in changes if item.get("@type") == "ActionUsage"
        )
        flow_payload = next(
            item for item in changes if item.get("@type") == "FlowConnectionUsage"
        )

        self.assertEqual(action_payload["name"], "1. Assess crossing condition")
        self.assertEqual(action_payload["owner"], {"@id": "owner-1"})
        self.assertEqual(
            action_payload["actionDefinition"], [{"@id": "definition-1"}]
        )
        self.assertEqual(flow_payload["name"], "Crossing status")
        self.assertEqual(flow_payload["owner"], {"@id": "owner-1"})
        self.assertEqual(
            flow_payload["flowConnectionDefinition"], [{"@id": "definition-1"}]
        )
        self.assertEqual(flow_payload["source"], [{"@id": "owner-1"}])
        self.assertEqual(flow_payload["target"], [{"@id": "owner-1"}])

        forbidden = {
            "Name",
            "Owner",
            "ActionDefinition",
            "FlowConnectionDefinition",
            "Source",
            "Target",
        }
        self.assertTrue(forbidden.isdisjoint(action_payload))
        self.assertTrue(forbidden.isdisjoint(flow_payload))


if __name__ == "__main__":
    unittest.main()
