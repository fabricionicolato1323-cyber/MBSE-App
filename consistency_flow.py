from __future__ import annotations

from model_consistency import compare_model_consistently, format_model_comparison, structural_issues
from terminal_ui import processing_indicator


class ConsistencyFlowMixin:
    """Feature 5 integration for deterministic model and RDF consistency checks."""

    def command(self, value: str) -> bool:
        raw = value.strip()
        cmd = raw.casefold()

        if cmd == "/compare":
            with processing_indicator("Comparing model consistency"):
                comparison = compare_model_consistently(self.knowledge, self.model)
            self.show_command_page(
                "MODEL CONSISTENCY COMPARISON",
                format_model_comparison(comparison),
            )
            return True

        if cmd == "/check":
            notes = list(self.model.completeness_messages())
            notes.extend(issue.message for issue in structural_issues(self.model))
            unique = list(dict.fromkeys(notes))
            body = (
                "\n".join(f"- {note}" for note in unique)
                if unique
                else "No obvious gap or structural inconsistency was found in the current model."
            )
            self.show_command_page("MODEL CHECK", body)
            return True

        return super().command(value)
