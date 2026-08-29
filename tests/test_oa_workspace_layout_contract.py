from pathlib import Path


def test_operational_analysis_is_the_active_viewpoint_with_placeholders():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert '<title>Operational Analysis · Guided Model Builder</title>' in html
    assert '>Operational Analysis</button>' in html
    assert '>System Analysis</button>' in html
    assert '>Logical Architecture</button>' in html
    assert '>Physical Architecture</button>' in html
    assert 'aria-disabled="true"' in html


def test_operational_analysis_purpose_objective_and_key_question_are_visible():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert '<strong>Purpose</strong>' in html
    assert '<strong>Objective</strong>' in html
    assert '<strong>Key question</strong>' in html
    assert 'before defining the solution' in html


def test_completion_panel_sits_between_conversation_and_model():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    chat_index = html.index('id="chatPanel"')
    completion_index = html.index('id="completionPanel"')
    model_index = html.index('id="modelPanel"')
    assert chat_index < completion_index < model_index
    assert 'id="completionPercent"' in html
    assert 'id="completionList"' in html


def test_all_three_panels_expose_dock_minimize_maximize_and_hide_controls():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert html.count('data-panel-action="dock"') == 3
    assert html.count('data-panel-action="minimize"') == 3
    assert html.count('data-panel-action="maximize"') == 3
    assert html.count('data-panel-action="close"') == 3
    assert html.count('data-panel-toggle=') == 3


def test_workspace_supports_resizing_floating_and_reopening_panels():
    script = Path('static/workspace_layout.js').read_text(encoding='utf-8')
    css = Path('static/workspace_layout.css').read_text(encoding='utf-8')
    assert 'setPanelVisible' in script
    assert 'undockPanel' in script
    assert 'dockPanel' in script
    assert 'installSplitter' in script
    assert "--completion-width" in script
    assert '.workspace-panel.is-floating' in css
    assert '.workspace-panel.is-minimized' in css
    assert '.workspace-panel.is-maximized' in css
    assert '16vw' in css


def test_completion_coverage_tracks_expected_operational_analysis_blocks():
    script = Path('static/workspace_layout.js').read_text(encoding='utf-8')
    expected_labels = [
        'Operational goal',
        'Participants / context',
        'Operational activities',
        'Activity ownership',
        'Operational interactions',
        'Communication means',
        'Characteristics / limits',
    ]
    for label in expected_labels:
        assert label in script
    assert 'weight: 15' in script
    assert 'renderOACompletion' in script
