from __future__ import annotations

from knowledge_graph import ModelComparison, ValidationIssue
from model_consistency import compare_model_consistently


_STANDARD_SCOPE_EXCLUDED_MESSAGES = {
    "The capability is not related to an operational mission.",
    "The capability is not yet described by an operational process or scenario.",
    "The interaction item does not yet reference domain data or concepts; this may limit content analysis.",
}


def _visible_in_standard_scope(issue: ValidationIssue) -> bool:
    if issue.severity == "VIOLATION":
        return True
    return issue.message not in _STANDARD_SCOPE_EXCLUDED_MESSAGES


def filter_current_scope_comparison(comparison: ModelComparison) -> ModelComparison:
    """Hide guidance for concepts that the current guided workflow cannot capture yet."""
    issues = tuple(
        issue
        for issue in comparison.issues
        if _visible_in_standard_scope(issue)
    )
    conforms = comparison.conforms and not any(
        issue.severity == "VIOLATION" for issue in issues
    )
    return ModelComparison(
        conforms=conforms,
        issues=issues,
        project_triples=comparison.project_triples,
        elapsed_ms=comparison.elapsed_ms,
    )


def compare_current_scope(knowledge, model) -> ModelComparison:
    """Use the integrated consistency engine, then present only currently actionable guidance."""
    return filter_current_scope_comparison(
        compare_model_consistently(knowledge, model)
    )


def format_current_scope_comparison(
    comparison: ModelComparison,
    max_issues: int | None = None,
) -> str:
    """Present consistency results without exposing RDF or internal identifiers."""
    violations = comparison.count("VIOLATION")
    warnings = comparison.count("WARNING")
    infos = comparison.count("INFO")

    lines = [
        f"Mandatory model rules: {'PASS' if comparison.conforms else 'FAIL'}",
        (
            "No structural inconsistencies found."
            if violations == 0
            else f"Structural inconsistencies: {violations}"
        ),
        f"Suggestions: {warnings} warning(s), {infos} information item(s)",
    ]

    selected = comparison.issues if max_issues is None else comparison.issues[:max_issues]
    if selected:
        lines.append("")
        for issue in selected:
            lines.append(
                f"- [{issue.severity}] {issue.focus_name}: {issue.message}"
            )

    if max_issues is not None and len(comparison.issues) > max_issues:
        lines.append(
            f"- ... {len(comparison.issues) - max_issues} more issue(s); "
            "use /compare to see all."
        )

    lines.extend(
        ["", f"Elapsed comparison time: {comparison.elapsed_ms:.1f} ms"]
    )
    return "\n".join(lines)
