from __future__ import annotations

import unittest

from sam_pysam_compat import install_transactional_factory_fix


class PySamTransactionalCompatibilityTests(unittest.TestCase):
    def test_transaction_factory_is_fixed_or_already_fixed_upstream(self) -> None:
        result = install_transactional_factory_fix()
        self.assertIn("required", result)
        self.assertIn("applied", result)

        from ansys.sam.sysml2.tools import Factory

        method = Factory._create_local_element_and_stack
        if result["required"]:
            self.assertTrue(result["applied"])
            self.assertTrue(getattr(method, "_mbse_level1_transaction_fix", False))
        else:
            # A future released PySAM may already contain the upstream correction.
            self.assertFalse(result["applied"])


if __name__ == "__main__":
    unittest.main()
