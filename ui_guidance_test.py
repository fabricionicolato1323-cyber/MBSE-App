import json
import os
import tempfile
from pathlib import Path

from guidance_flow import GuidanceFlowMixin
from ontology import CONCEPT_GUIDANCE
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
    forbidden = (
        "operations coordinator",
        "fire brigade",
        "control tower",
        "maintain safe",
        "maintain timely operational awareness",
        "assess the situation",
        "coordinate service requests",
        "status information",
        "direct communication",
    )

    # 1. Repository defaults are neutral placeholders, not scenario examples.
    data = load_ui_guidance()
    examples = data.get("examples_by_expected_structure", {})
    assert examples
    assert not literal_domain_examples_allowed()

    serialized = json.dumps(examples).casefold()
    assert not any(term in serialized for term in forbidden)
    assert all("<" in str(value) for value in examples.values())

    # 2. Semantic concept guidance contains definitions/formats, not examples.
    assert all("example" not in guidance for guidance in CONCEPT_GUIDANCE.values())

    # 3. Active runtime Python no longer contains the former literal examples.
    root = Path(__file__).resolve().parent
    runtime_files = (
        "app_base.py",
        "participant_flow.py",
        "composition_flow.py",
        "ontology.py",
    )
    runtime_text = "\n".join(
        (root / filename).read_text(encoding="utf-8").casefold()
        for filename in runtime_files
    )
    assert not any(term in runtime_text for term in forbidden)

    # 4. A literal example passed by compatibility code is ignored at the render boundary.
    app = DummyApp()
    structure = "verb + desired state/object [+ optional complement]"
    app.draw_question(
        "Question",
        example="Scenario-specific literal",
        expected_structure=structure,
    )
    assert app.rendered_example == configured_example(structure)
    assert app.rendered_example != "Scenario-specific literal"

    # 5. Guidance can be replaced externally without changing Python code.
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

    print("UI guidance test passed (5 policy checks).")


if __name__ == "__main__":
    main()
