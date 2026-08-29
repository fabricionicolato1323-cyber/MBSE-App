from __future__ import annotations

from current_scope import compare_current_scope, format_current_scope_comparison
from model_consistency import structural_issues
from terminal_ui import processing_indicator


class ConsistencyFlowMixin:
    """Integrated deterministic model and RDF consistency checks."""

    def command(self, value: str) -> bool:
        raw = value.strip()
        cmd = raw.casefold()

        if cmd == "/compare":
            with processing_indicator("Comparing model consistency"):
                comparison = compare_current_scope(self.knowledge, self.model)
            self.show_command_page(
                "MODEL CONSISTENCY COMPARISON",
                format_current_scope_comparison(comparison),
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
