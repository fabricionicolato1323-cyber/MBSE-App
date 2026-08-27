from __future__ import annotations

import argparse
from pathlib import Path

from graph_model import OAGraph
from knowledge_graph import ArcadiaKnowledgeBase


BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_BASE_DIR = BASE_DIR / "knowledge_base"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export a saved OA model as canonical JSON, approved RDF Turtle, "
            "and a SHACL validation report."
        )
    )
    parser.add_argument("model", type=Path, help="Path to oa_model.json")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BASE_DIR / "export",
        help="Directory for exported artifacts (default: ./export)",
    )
    parser.add_argument(
        "--migrate-legacy",
        action="store_true",
        help=(
            "Explicitly approve migration of a legacy name-based model identity "
            "to canonical UUIDs."
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    model = OAGraph.load(args.model, allow_migration=args.migrate_legacy)
    knowledge = ArcadiaKnowledgeBase(KNOWLEDGE_BASE_DIR)
    artifacts = knowledge.export_approved_model(model, args.output_dir)

    if model.graph.graph.get("migrated_from_legacy"):
        print("Legacy model identity migrated to UUIDs in the exported copy.")
        print("The original source file was not overwritten.")

    print(f"JSON: {artifacts.json_path}")
    print(f"Approved RDF: {artifacts.turtle_path}")
    print(f"Validation report: {artifacts.validation_report_path}")
    print(
        "Validation: "
        f"{artifacts.comparison.count('VIOLATION')} violation(s), "
        f"{artifacts.comparison.count('WARNING')} warning(s), "
        f"{artifacts.comparison.count('INFO')} information item(s)"
    )
    print(f"Elapsed comparison time: {artifacts.comparison.elapsed_ms:.1f} ms")


if __name__ == "__main__":
    main()
