from __future__ import annotations

import json
from pathlib import Path

import pytest

from sam_reference_profile import (
    DEFAULT_SAM_REFERENCE_PROFILE,
    SAMReferenceProfileError,
    load_sam_reference_profile,
)


def test_reference_profile_loads_and_preserves_sam_library_shape() -> None:
    profile = DEFAULT_SAM_REFERENCE_PROFILE

    assert profile.exported_library_package == "Arcadia_OA_libray"
    assert profile.definition("OperationalEntity")["definition_kind"] == "part"
    assert profile.definition("OperationalActor")["specializes"] == "OperationalEntity"
    assert profile.definition("OperationalActivity")["definition_kind"] == "action"
    assert profile.definition("OperationalCapability")["definition_kind"] == "requirement"
    assert profile.definition("OperationalExchange")["sysml_name"] == "Operational Iteration"
    assert profile.definition("OperationalExchange")["definition_kind"] == "flow"
    assert profile.definition("OperationalScenario")["definition_kind"] == "action"


def test_communication_mean_is_library_only_for_this_phase() -> None:
    profile = DEFAULT_SAM_REFERENCE_PROFILE

    assert profile.definition("CommunicationMean")["definition_kind"] == "interface"
    assert profile.projection_enabled("CommunicationMean") is False
    assert profile.definition("CommunicationMean")["projection_policy"] == "library_definition_only"
    assert profile.contract["model_structure"]["placement"]["CommunicationMean"] == "excluded"


def test_reference_profile_contains_no_model_instances() -> None:
    text = DEFAULT_SAM_REFERENCE_PROFILE.sysml_text

    # The reference file is a library only: model usages belong to generated output,
    # never to the structural profile.
    assert "package Arcadia_OA {" not in text
    assert "part '" not in text
    assert "perform action" not in text
    assert "transition" not in text


def test_invalid_communication_projection_is_rejected(tmp_path: Path) -> None:
    source_contract = DEFAULT_SAM_REFERENCE_PROFILE.contract
    modified = json.loads(json.dumps(source_contract))
    modified["definitions"]["CommunicationMean"]["projection_enabled"] = True

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(modified), encoding="utf-8")
    sysml_path = tmp_path / "reference.sysml"
    sysml_path.write_text(DEFAULT_SAM_REFERENCE_PROFILE.sysml_text, encoding="utf-8")

    with pytest.raises(SAMReferenceProfileError, match="CommunicationMean"):
        load_sam_reference_profile(sysml_path=sysml_path, profile_path=profile_path)
