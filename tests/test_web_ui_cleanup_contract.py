from pathlib import Path


def test_command_bar_is_not_rendered_as_buttons():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert 'data-command="/why"' not in html
    assert 'data-command="/undo"' not in html
    assert '<div id="commandBar" hidden></div>' in html


def test_structured_prompt_redundancy_is_filtered():
    script = Path('static/revision_interaction.js').read_text(encoding='utf-8')
    assert "replace(/\\s*\\(yes\\/no\\)" in script
    assert "^Expected answer:" in script
    assert "^Answer only" in script
    assert "revisionRequestInFlight" in script
    assert "revisionQuestionTools" in script


def test_structured_buttons_are_not_rebuilt_on_every_poll():
    script = Path('static/revision_interaction.js').read_text(encoding='utf-8')
    css = Path('static/revision.css').read_text(encoding='utf-8')
    assert "revisionLastInteractionSignature" in script
    assert "revisionInteractionSignature" in script
    assert "stableStructuredDom" in script
    assert "quickRoot.childElementCount === expectedButtonCount" in script
    assert "transform: none" in css


def test_stable_structured_buttons_are_reenabled_when_ready():
    script = Path('static/revision_interaction.js').read_text(encoding='utf-8')
    assert "revisionSetStructuredButtonsEnabled" in script
    assert "const controlsEnabled = waiting && !busy && !locked" in script
    assert "revisionSetStructuredButtonsEnabled(quickRoot, controlsEnabled)" in script
    assert "button.disabled = !controlsEnabled" in script


def test_unexpected_worker_exit_is_not_reported_as_normal_finish():
    script = Path('static/revision_interaction.js').read_text(encoding='utf-8')
    assert "stopped unexpectedly" in script
    assert "Modeling session finished" in script
