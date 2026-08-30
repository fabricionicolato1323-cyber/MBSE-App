from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LIBRARY_DIR = Path(__file__).resolve().parent / "sysml"
DEFAULT_SYSML_PATH = LIBRARY_DIR / "ArcadiaOA.sysml"
DEFAULT_CONTRACT_PATH = LIBRARY_DIR / "ArcadiaOA.translation.json"


class ArcadiaOALibraryError(ValueError):
    """Raised when the ArcadiaOA translation library is incomplete or inconsistent."""


@dataclass(frozen=True)
class ArcadiaOALibrary:
    sysml_text: str
    contract: dict[str, Any]

    @property
    def package_name(self) -> str:
        library = self.contract.get("library", {})
        return str(library.get("package") or "").strip()


def _definition_pattern(keyword: str, definition: str) -> re.Pattern[str]:
    escaped = re.escape(definition)
    if keyword == "part":
        head = r"part\s+def"
    elif keyword == "action":
        head = r"action\s+def"
    elif keyword == "item":
        head = r"item\s+def"
    elif keyword == "flow":
        head = r"flow\s+def"
    elif keyword == "connection":
        head = r"connection\s+def"
    elif keyword == "requirement":
        head = r"requirement\s+def"
    else:
        raise ArcadiaOALibraryError(
            f"Unsupported SysML definition keyword in ArcadiaOA contract: {keyword!r}"
        )
    return re.compile(rf"\b{head}\s+{escaped}\b")


def _require_definition(text: str, keyword: str, definition: str, context: str) -> None:
    if not keyword or not definition:
        raise ArcadiaOALibraryError(
            f"ArcadiaOA contract is missing {context} definition information."
        )
    if not _definition_pattern(keyword, definition).search(text):
        raise ArcadiaOALibraryError(
            f"ArcadiaOA contract maps {context} to {keyword} def {definition}, "
            "but that definition does not exist in ArcadiaOA.sysml."
        )


def validate_arcadia_oa_library(library: ArcadiaOALibrary) -> ArcadiaOALibrary:
    contract = library.contract
    if int(contract.get("schema_version", 0)) != 1:
        raise ArcadiaOALibraryError(
            "ArcadiaOA translation contract schema_version must be 1."
        )

    package = library.package_name
    if not package:
        raise ArcadiaOALibraryError(
            "ArcadiaOA translation contract must name its library package."
        )
    if not re.search(rf"\bpackage\s+{re.escape(package)}\s*\{{", library.sysml_text):
        raise ArcadiaOALibraryError(
            f"ArcadiaOA.sysml does not declare the package required by the contract: {package}."
        )

    node_mappings = contract.get("node_types", {})
    if not isinstance(node_mappings, dict) or not node_mappings:
        raise ArcadiaOALibraryError(
            "ArcadiaOA translation contract must define node_types."
        )
    for source_type, mapping in node_mappings.items():
        if not isinstance(mapping, dict):
            raise ArcadiaOALibraryError(f"Invalid node mapping for {source_type!r}.")
        _require_definition(
            library.sysml_text,
            str(mapping.get("usage_keyword") or ""),
            str(mapping.get("definition") or ""),
            f"node type {source_type!r}",
        )
        if not str(mapping.get("identifier_prefix") or "").strip():
            raise ArcadiaOALibraryError(
                f"Node mapping {source_type!r} needs identifier_prefix."
            )

    relations = contract.get("relationships", {})
    if not isinstance(relations, dict):
        raise ArcadiaOALibraryError(
            "ArcadiaOA translation contract relationships must be an object."
        )
    allowed_strategies = {
        "containment",
        "perform",
        "flow",
        "connection",
        "unmapped",
    }
    for relation, mapping in relations.items():
        if not isinstance(mapping, dict):
            raise ArcadiaOALibraryError(
                f"Invalid relationship mapping for {relation!r}."
            )
        strategy = str(mapping.get("strategy") or "")
        if strategy not in allowed_strategies:
            raise ArcadiaOALibraryError(
                f"Relationship {relation!r} uses unsupported ArcadiaOA "
                f"translation strategy {strategy!r}."
            )
        if strategy in {"flow", "connection"}:
            _require_definition(
                library.sysml_text,
                strategy,
                str(mapping.get("definition") or ""),
                f"relationship {relation!r}",
            )
        if strategy == "flow":
            payload = str(mapping.get("payload_definition") or "")
            _require_definition(
                library.sysml_text,
                "item",
                payload,
                f"payload for relationship {relation!r}",
            )

    scenario = contract.get("operational_scenario", {})
    if scenario:
        if not isinstance(scenario, dict):
            raise ArcadiaOALibraryError(
                "operational_scenario mapping must be an object."
            )
        _require_definition(
            library.sysml_text,
            str(scenario.get("usage_keyword") or ""),
            str(scenario.get("definition") or ""),
            "Operational Scenario",
        )
        _require_definition(
            library.sysml_text,
            str(scenario.get("activity_usage_keyword") or ""),
            str(scenario.get("activity_definition") or ""),
            "Operational Scenario activity step",
        )
        interaction_relation = str(scenario.get("interaction_relation") or "")
        relation_mapping = relations.get(interaction_relation)
        if (
            not isinstance(relation_mapping, dict)
            or relation_mapping.get("strategy") != "flow"
        ):
            raise ArcadiaOALibraryError(
                "Operational Scenario interaction_relation must reference a flow "
                "relationship declared by ArcadiaOA."
            )

    characteristics = contract.get("characteristics", {})
    if characteristics:
        if characteristics.get("strategy") != "attributes":
            raise ArcadiaOALibraryError(
                "Only the ArcadiaOA-declared attributes characteristic strategy "
                "is supported."
            )
        scalar_types = characteristics.get("scalar_types", {})
        required = {"integer", "real", "string"}
        if (
            not isinstance(scalar_types, dict)
            or not required.issubset(scalar_types)
        ):
            raise ArcadiaOALibraryError(
                "ArcadiaOA characteristics must declare integer, real, and string "
                "scalar types."
            )

    policy = contract.get("policy", {})
    if policy.get("unknown_mapping") != "comment_only":
        raise ArcadiaOALibraryError(
            "ArcadiaOA must use comment_only for unknown mappings; semantic "
            "fallback generation is forbidden."
        )
    if policy.get("temporary_content") != "comment_only":
        raise ArcadiaOALibraryError(
            "ArcadiaOA temporary_content policy must be comment_only."
        )
    if policy.get("semantic_fallback") != "forbidden":
        raise ArcadiaOALibraryError(
            "ArcadiaOA semantic_fallback policy must be forbidden."
        )

    return library


def load_arcadia_oa_library(
    *,
    sysml_path: Path | None = None,
    contract_path: Path | None = None,
) -> ArcadiaOALibrary:
    sysml_file = Path(sysml_path or DEFAULT_SYSML_PATH)
    contract_file = Path(contract_path or DEFAULT_CONTRACT_PATH)
    try:
        text = sysml_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArcadiaOALibraryError(
            f"Cannot read ArcadiaOA SysML library: {sysml_file}"
        ) from exc
    try:
        contract = json.loads(contract_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArcadiaOALibraryError(
            f"Cannot read ArcadiaOA translation contract: {contract_file}"
        ) from exc
    if not isinstance(contract, dict):
        raise ArcadiaOALibraryError(
            "ArcadiaOA translation contract root must be an object."
        )
    return validate_arcadia_oa_library(ArcadiaOALibrary(text, contract))


DEFAULT_ARCADIA_OA_LIBRARY = load_arcadia_oa_library()
