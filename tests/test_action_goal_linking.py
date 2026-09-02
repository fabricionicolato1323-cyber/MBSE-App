from action_goal_linking import ActionGoalLinkingMixin


class _FakeGraph:
    def __contains__(self, item: str) -> bool:
        return item == "action-1"

    def out_edges(self, node_id: str, data: bool = False):
        return []


class _FakeModel:
    def __init__(self) -> None:
        self.graph = _FakeGraph()
        self.links: list[tuple[str, str, str]] = []
        self.names = {
            "action-1": "Detect threat",
            "goal-1": "Keep area safe",
            "goal-2": "Protect personnel",
        }

    def name(self, node_id: str) -> str:
        return self.names[node_id]

    def nodes_of_type(self, node_type: str) -> list[str]:
        if node_type == "OperationalCapability":
            return ["goal-1", "goal-2"]
        if node_type == "OperationalActivity":
            return ["action-1"]
        return []

    def has_relation(self, source: str, relation: str, target: str) -> bool:
        return (source, relation, target) in self.links

    def add_relation(self, source: str, relation: str, target: str):
        self.links.append((source, relation, target))
        return True, ""


class _FakeFlow(ActionGoalLinkingMixin):
    def __init__(self) -> None:
        self.model = _FakeModel()
        self.choice_answers = ["goal-1", "goal-2"]
        self.yes_no_answers = [True, False]
        self.questions: list[str] = []

    def _goals_for_action(self, action_id: str) -> list[str]:
        return [target for source, relation, target in self.model.links if source == action_id and relation == "SUPPORTS_CAPABILITY"]

    def ask_choice(self, question, choices, why):
        self.questions.append(question)
        return self.choice_answers.pop(0)

    def ask_yes_no(self, question, why):
        self.questions.append(question)
        return self.yes_no_answers.pop(0)

    def ask_validated(self, **kwargs):
        raise AssertionError("No new goal should be required in this test.")

    def add_node(self, *args, **kwargs):
        raise AssertionError("No new goal should be required in this test.")

    def add_notice(self, message: str) -> None:
        raise AssertionError(message)


def test_every_new_action_gets_explicit_goal_and_can_get_multiple_goals() -> None:
    flow = _FakeFlow()
    flow.link_action_to_goal("action-1")

    assert flow.model.links == [
        ("action-1", "SUPPORTS_CAPABILITY", "goal-1"),
        ("action-1", "SUPPORTS_CAPABILITY", "goal-2"),
    ]
    assert flow.questions[0] == "Which goal does 'Detect threat' contribute to?"
    assert "another goal" in flow.questions[1]
    assert "additional goal" in flow.questions[2]


if __name__ == "__main__":
    test_every_new_action_gets_explicit_goal_and_can_get_multiple_goals()
    print("Action goal linking test passed.")
