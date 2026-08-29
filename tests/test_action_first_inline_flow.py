from action_first_inline_flow import ActionFirstInlineCreationMixin


class _FakeModel:
    def action_label(self, node_id: str) -> str:
        return node_id


class _FakeFlow(ActionFirstInlineCreationMixin):
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.model = _FakeModel()

    def _capture_inline_action_text(self) -> str:
        self.events.append(("action",))
        return "Process request"

    def _select_performer_for_inline_action(self, action_text: str) -> str:
        self.events.append(("performer", action_text))
        return "participant-1"

    def _interpret_inline_action_text(self, performer_id: str, source_text: str) -> dict:
        self.events.append(("interpret", performer_id, source_text))
        return {"clauses": [{"activity_text": source_text}]}

    def create_activity_from_frame(
        self,
        clause: dict,
        performer_id: str,
        source_text: str,
    ) -> str:
        self.events.append(
            ("create", clause["activity_text"], performer_id, source_text)
        )
        return "action-1"

    def add_notice(self, message: str) -> None:
        self.events.append(("notice", message))

    def ask_number(self, *args, **kwargs) -> str:
        raise AssertionError("Single created action should not require selection.")


def test_inline_action_is_described_before_performer_selection() -> None:
    flow = _FakeFlow()

    created = flow._create_new_action_reference()

    assert created == "action-1"
    assert flow.events[:4] == [
        ("action",),
        ("performer", "Process request"),
        ("interpret", "participant-1", "Process request"),
        ("create", "Process request", "participant-1", "Process request"),
    ]


if __name__ == "__main__":
    test_inline_action_is_described_before_performer_selection()
    print("Action-first inline creation test passed.")
