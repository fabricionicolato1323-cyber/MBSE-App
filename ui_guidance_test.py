import json
import os
import tempfile
from pathlib import Path

from guidance_flow import GuidanceFlowMixin
from ui_guidance import (
    GUIDANCE_ENV,
    configured_example,
    literal_domain_examples_allowed,
    load_ui_guidance,
)


class CaptureBase:
    def __init__(self) -> None:
        self.rendered_example = None

    def draw_question(
        self,
        question: str,
        explanation: str = "",
        example: str = "",
        expected_structure: str = "",
        extra_lines=None,
    ) -> None:
        self.rendered_example = example


class DummyApp(GuidanceFlowMixin, CaptureBase):
    pass


def main() -> None:
    # 1. Repository defaults are neutral placeholders, not scenario examples.
    data = load_ui_guidance()
    examples = data.get("examples_by_expected_structure", {})
    assert examples
    assert not literal_domain_examples_allowed()

    serialized = json.dumps(examples).casefold()
    forbidden = (
        "operations coordinator",
        "fire brigade",
        "control tower",
        "maintain safe",
        "assess the situation",
        "status information",
        "direct communication",
    )
    assert not any(term in serialized for term in forbidden)
    assert all("<" in str(value) for value in examples.values())

    # 2. A literal example passed by legacy code is ignored at the render boundary.
    app = DummyApp()
    structure = "verb + desired state/object [+ optional complement]"
    app.draw_question(
        "Question",
        example="Scenario-specific literal",
        expected_structure=structure,
    )
    assert app.rendered_example == configured_example(structure)
    assert app.rendered_example != "Scenario-specific literal"

    # 3. Guidance can be replaced externally without changing Python code.
    previous = os.environ.get(GUIDANCE_ENV)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ui_guidance.json"
        path.write_text(
            json.dumps(
                {
                    "examples_by_expected_structure": {
                        structure: "<custom neutral placeholder>"
                    },
                    "policy": {"allow_literal_domain_examples": False},
                }
            ),
            encoding="utf-8",
        )
        os.environ[GUIDANCE_ENV] = str(path)
        load_ui_guidance.cache_clear()
        assert configured_example(structure) == "<custom neutral placeholder>"

    if previous is None:
        os.environ.pop(GUIDANCE_ENV, None)
    else:
        os.environ[GUIDANCE_ENV] = previous
    load_ui_guidance.cache_clear()

    print("UI guidance test passed (3 policy checks).")


if __name__ == "__main__":
    main()
