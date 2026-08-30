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


def test_default_layout_is_completion_conversation_then_text_sysml():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    completion_index = html.index('id="completionPanel"')
    chat_index = html.index('id="chatPanel"')
    model_index = html.index('id="modelPanel"')
    assert completion_index < chat_index < model_index
    assert 'id="completionPercent"' in html
    assert 'id="completionList"' in html
    assert 'data-panel-toggle="model">Text / SysML V2</button>' in html


def test_text_and_sysml_v2_are_primary_textual_output_tabs():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert 'data-utility-tab="text"' in html
    assert 'data-utility-tab="sysml"' in html
    assert '>Text</button>' in html
    assert '>SysML V2</button>' in html
    assert 'SysML V2 textual output' in html
    assert 'intentionally text-based, not a block diagram' in html
    assert 'Generated SysML V2 text will appear here' in html


def test_existing_model_views_remain_available_inside_text_output():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert 'data-tab="textual"' in html
    assert 'data-tab="diagram"' in html
    assert 'data-tab="details"' in html
    assert 'id="modelTextual"' in html
    assert 'id="modelDiagram"' in html
    assert 'id="modelDetails"' in html


def test_all_three_panels_keep_dock_minimize_maximize_and_hide_controls():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert html.count('data-panel-action="dock"') == 3
    assert html.count('data-panel-action="minimize"') == 3
    assert html.count('data-panel-action="maximize"') == 3
    assert html.count('data-panel-action="close"') == 3
    assert html.count('data-panel-toggle=') == 3


def test_workspace_supports_resizing_floating_reopening_and_browser_undock():
    script = Path('static/workspace_layout.js').read_text(encoding='utf-8')
    css = Path('static/workspace_layout.css').read_text(encoding='utf-8')
    assert 'setPanelVisible' in script
    assert 'undockPanel' in script
    assert 'dockPanel' in script
    assert 'openUtilityBrowserWindow' in script
    assert 'redockUtilityPanel' in script
    assert 'window.open' in script
    assert "detachedPanel', 'utility'" in script
    assert 'requestFullscreen' in script
    assert 'installSplitter' in script
    assert "--completion-width" in script
    assert '.workspace-panel.is-floating' in css
    assert '.workspace-panel.is-minimized' in css
    assert '.workspace-panel.is-maximized' in css
    assert 'body.detached-utility-window' in css


def test_splitter_directions_match_left_completion_and_right_output_panel():
    script = Path('static/workspace_layout.js').read_text(encoding='utf-8')
    assert "panelName === 'completion'" in script
    assert '? startWidth + delta' in script
    assert ': startWidth - delta' in script
    assert "panelIsDockedUsable('completion') && panelIsDockedUsable('chat')" in script
    assert "panelIsDockedUsable('chat') && panelIsDockedUsable('model')" in script


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
