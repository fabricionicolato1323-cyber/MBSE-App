from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REFERENCE_DIR = Path(__file__).resolve().parent / "sysml"
DEFAULT_REFERENCE_SYSML_PATH = REFERENCE_DIR / "SAM_OA.reference.sysml"
DEFAULT_REFERENCE_PROFILE_PATH = REFERENCE_DIR / "SAM_OA.reference.json"


class SAMReferenceProfileError(ValueError):
    """Raised when the declarative SAM OA reference profile is inconsistent."""


@dataclass(frozen=True)
class SAMReferenceProfile:
    sysml_text: str
    contract: dict[str, Any]

    @property
    def exported_library_package(self) -> str:
        library = self.contract.get("library", {})
        return str(library.get("exported_package") or "").strip()

    @property
    def definitions(self) -> dict[str, dict[str, Any]]:
        value = self.contract.get("definitions", {})
        return value if isinstance(value, dict) else {}

    @property
    def relationships(self) -> dict[str, dict[str, Any]]:
        value = self.contract.get("relationships", {})
        return value if isinstance(value, dict) else {}

    def definition(self, concept: str) -> dict[str, Any]:
        value = self.definitions.get(concept)
        if not isinstance(value, dict):
            raise SAMReferenceProfileError(
                f"SAM reference profile has no definition for {concept!r}."
            )
        return value

    def relationship(self, relation: str) -> dict[str, Any]:
        value = self.relationships.get(relation)
        if not isinstance(value, dict):
            raise SAMReferenceProfileError(
                f"SAM reference profile has no relationship mapping for {relation!r}."
            )
        return value

    def projection_enabled(self, concept: str) -> bool:
        return bool(self.definition(concept).get("projection_enabled", False))


_DEFINITION_HEADS = {
    "part": r"part\s+def",
    "action": r"action\s+def",
    "requirement": r"requirement\s+def",
    "flow": r"flow\s+def",
    "interface": r"interface\s+def",
    "constraint": r"constraint\s+def",
}


def _quoted_name(name: str) -> str:
    return rf"(?:'{re.escape(name)}'|{re.escape(name)})"


def _definition_pattern(kind: str, name: str) -> re.Pattern[str]:
    head = _DEFINITION_HEADS.get(kind)
    if head is None:
        raise SAMReferenceProfileError(
            f"Unsupported SAM reference definition kind: {kind!r}."
        )
    return re.compile(rf"\b{head}\s+{_quoted_name(name)}(?=\s|;|\{{|:)")


def _require_definition(text: str, concept: str, mapping: dict[str, Any]) -> None:
    name = str(mapping.get("sysml_name") or "").strip()
    kind = str(mapping.get("definition_kind") or "").strip()
    if not name or not kind:
        raise SAMReferenceProfileError(
            f"SAM reference definition {concept!r} needs sysml_name and definition_kind."
        )
    if not _definition_pattern(kind, name).search(text):
        raise SAMReferenceProfileError(
            f"SAM reference maps {concept!r} to {kind} def {name!r}, "
            "but that declaration is missing from SAM_OA.reference.sysml."
        )


def _validate_endpoint_types(
    relation: str,
    mapping: dict[str, Any],
    definitions: dict[str, dict[str, Any]],
) -> None:
    endpoint_types: set[str] = set(mapping.get("source_node_types") or [])
    endpoint_types.update(mapping.get("target_node_types") or [])
    variants = mapping.get("variants")
    if isinstance(variants, list):
        for variant in variants:
            if not isinstance(variant, dict):
                raise SAMReferenceProfileError(
                    f"SAM relationship mapping {relation!r} has an invalid variant."
                )
            endpoint_types.add(str(variant.get("source_node_type") or ""))
            endpoint_types.add(str(variant.get("target_node_type") or ""))
    unknown = sorted(value for value in endpoint_types if value and value not in definitions)
    if unknown:
        raise SAMReferenceProfileError(
            f"SAM relationship mapping {relation!r} references unknown node types: "
            + ", ".join(unknown)
        )


def validate_sam_reference_profile(profile: SAMReferenceProfile) -> SAMReferenceProfile:
    contract = profile.contract
    if int(contract.get("schema_version", 0)) != 1:
        raise SAMReferenceProfileError("SAM OA reference profile schema_version must be 1.")

    provenance = contract.get("provenance", {})
    if not isinstance(provenance, dict):
        raise SAMReferenceProfileError("SAM reference provenance must be an object.")
    if provenance.get("purpose") != "structural_reference_only":
        raise SAMReferenceProfileError(
            "SAM reference profile must be structural_reference_only."
        )
    if provenance.get("instance_content") != "forbidden":
        raise SAMReferenceProfileError(
            "SAM reference profile must forbid instance content."
        )

    package = profile.exported_library_package
    if not package:
        raise SAMReferenceProfileError(
            "SAM reference profile must declare library.exported_package."
        )
    if not re.search(rf"\bpackage\s+{re.escape(package)}\s*\{{", profile.sysml_text):
        raise SAMReferenceProfileError(
            "SAM reference SysML does not declare the exported library package "
            f"required by the profile: {package!r}."
        )

    definitions = profile.definitions
    required_concepts = {
        "OperationalScenario",
        "OperationalEntity",
        "OperationalActor",
        "OperationalCapability",
        "OperationalExchange",
        "CommunicationMean",
        "OperationalConstraint",
        "OperationalActivity",
    }
    missing = sorted(required_concepts - set(definitions))
    if missing:
        raise SAMReferenceProfileError(
            "SAM reference profile is missing required definitions: " + ", ".join(missing)
        )
    for concept, mapping in definitions.items():
        if not isinstance(mapping, dict):
            raise SAMReferenceProfileError(
                f"SAM reference definition {concept!r} must be an object."
            )
        _require_definition(profile.sysml_text, concept, mapping)

    actor = profile.definition("OperationalActor")
    if str(actor.get("specializes") or "").strip() != "OperationalEntity":
        raise SAMReferenceProfileError(
            "OperationalActor must specialize OperationalEntity in the SAM reference profile."
        )
    parent_name = str(profile.definition("OperationalEntity").get("sysml_name") or "").strip()
    actor_name = str(actor.get("sysml_name") or "").strip()
    specialization = re.compile(
        rf"\bpart\s+def\s+{_quoted_name(actor_name)}\s*:>\s*{_quoted_name(parent_name)}"
    )
    if not specialization.search(profile.sysml_text):
        raise SAMReferenceProfileError(
            "SAM reference SysML must preserve Operational Actor specialization of Operational Entity."
        )

    communication = profile.definition("CommunicationMean")
    if communication.get("projection_enabled") is not False:
        raise SAMReferenceProfileError(
            "CommunicationMean must remain disabled for SAM projection in this phase."
        )
    if communication.get("projection_policy") != "library_definition_only":
        raise SAMReferenceProfileError(
            "CommunicationMean must use library_definition_only projection policy."
        )
    if profile.definition("OperationalExchange").get("definition_kind") != "flow":
        raise SAMReferenceProfileError(
            "OperationalExchange must use the SAM-exported flow definition structure."
        )

    structure = contract.get("model_structure", {})
    if not isinstance(structure, dict):
        raise SAMReferenceProfileError("model_structure must be an object.")
    containers = structure.get("containers", {})
    if containers != {
        "structure": "Structure",
        "requirements": "Requirements",
        "scenarios": "Scenarios",
    }:
        raise SAMReferenceProfileError(
            "SAM reference containers must be Structure, Requirements, and Scenarios."
        )
    placement = structure.get("placement", {})
    if not isinstance(placement, dict):
        raise SAMReferenceProfileError("model_structure.placement must be an object.")
    if placement.get("OperationalActivity") != "performer_nested":
        raise SAMReferenceProfileError(
            "OperationalActivity must be nested under its performer in the SAM reference profile."
        )
    if placement.get("CommunicationMean") != "excluded":
        raise SAMReferenceProfileError(
            "CommunicationMean must be excluded from model projection in this phase."
        )

    relationships = profile.relationships
    expected_relationships = {
        "CONTAINS": "nested_part",
        "PERFORMS": "activity_owner",
        "DECOMPOSES": "nested_usage",
        "OPERATIONAL_EXCHANGE": "flow",
        "SUPPORTS_CAPABILITY": "allocation",
        "LOCATED_IN": "reference",
        "COMMUNICATION_MEAN": "ignore",
    }
    for relation, strategy in expected_relationships.items():
        mapping = relationships.get(relation)
        if not isinstance(mapping, dict) or mapping.get("strategy") != strategy:
            raise SAMReferenceProfileError(
                f"SAM relationship mapping {relation!r} must use strategy {strategy!r}."
            )
        _validate_endpoint_types(relation, mapping, definitions)
    if profile.relationship("COMMUNICATION_MEAN").get("reason") != "projection_disabled_for_current_phase":
        raise SAMReferenceProfileError(
            "Communication Mean relationship mapping must explicitly record the current phase exclusion."
        )

    rules = contract.get("projection_rules", {})
    if not isinstance(rules, dict):
        raise SAMReferenceProfileError("projection_rules must be an object.")
    expected_rules = {
        "participant_containment": "nested_part_usage",
        "activity_ownership": "nested_usage",
        "decomposition": "nested_usage",
        "operational_exchange": "flow_between_qualified_activity_paths",
        "supports_capability": "allocation",
        "located_in": "reference_usage",
        "characteristics": "attribute_usage",
        "scenario_activity": "perform_action_reference",
        "scenario_sequence": "transition_first_then",
        "communication_mean": "excluded_from_projection",
    }
    for rule, strategy in expected_rules.items():
        value = rules.get(rule)
        if not isinstance(value, dict) or value.get("strategy") != strategy:
            raise SAMReferenceProfileError(
                f"SAM reference projection rule {rule!r} must use strategy {strategy!r}."
            )

    return profile


def load_sam_reference_profile(
    *,
    sysml_path: Path | None = None,
    profile_path: Path | None = None,
) -> SAMReferenceProfile:
    sysml_file = Path(sysml_path or DEFAULT_REFERENCE_SYSML_PATH)
    contract_file = Path(profile_path or DEFAULT_REFERENCE_PROFILE_PATH)
    try:
        sysml_text = sysml_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise SAMReferenceProfileError(
            f"Cannot read SAM OA reference SysML: {sysml_file}"
        ) from exc
    try:
        contract = json.loads(contract_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SAMReferenceProfileError(
            f"Cannot read SAM OA reference profile: {contract_file}"
        ) from exc
    if not isinstance(contract, dict):
        raise SAMReferenceProfileError("SAM OA reference profile root must be an object.")
    return validate_sam_reference_profile(SAMReferenceProfile(sysml_text, contract))


DEFAULT_SAM_REFERENCE_PROFILE = load_sam_reference_profile()
