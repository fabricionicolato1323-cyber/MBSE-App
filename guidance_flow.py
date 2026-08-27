from __future__ import annotations

from ui_guidance import configured_example, literal_domain_examples_allowed


class GuidanceFlowMixin:
    """Apply external, domain-neutral UI examples at the rendering boundary.

    Existing callers may still pass legacy example strings, but they are ignored
    by default. This prevents domain examples embedded in older flow code from
    influencing the user while the code is incrementally cleaned up.
    """

    def draw_question(
        self,
        question: str,
        explanation: str = "",
        example: str = "",
        expected_structure: str = "",
        extra_lines: list[str] | None = None,
    ) -> None:
        if literal_domain_examples_allowed():
            display_example = example
        else:
            display_example = configured_example(expected_structure)

        super().draw_question(
            question,
            explanation=explanation,
            example=display_example,
            expected_structure=expected_structure,
            extra_lines=extra_lines,
        )
