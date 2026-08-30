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


def test_default_layout_is_completion_conversation_then_single_output_sidebar():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    completion_index = html.index('id="completionPanel"')
    chat_index = html.index('id="chatPanel"')
    output_index = html.index('id="modelPanel"')
    assert completion_index < chat_index < output_index
    assert 'id="completionPercent"' in html
    assert 'id="completionList"' in html
    assert 'data-panel-toggle="output">Model output</button>' in html
    assert 'id="sysmlPanel"' not in html


def test_docked_output_sidebar_has_four_primary_views():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    for view in ['text', 'sysml', 'diagram', 'details']:
        assert f'data-output-tab="{view}"' in html
        assert f'data-output-view="{view}"' in html
    assert '>Pseudo-code</button>' in html
    assert '>SysML V2</button>' in html
    assert '>Diagram</button>' in html
    assert '>Details</button>' in html
    assert 'SysML V2 textual output' in html
    assert 'intentionally text-based, not a block diagram' in html
    assert 'Generated SysML V2 text will appear here' in html


def test_existing_render_targets_remain_available_in_unified_sidebar():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert 'id="modelTextual"' in html
    assert 'id="modelDiagram"' in html
    assert 'id="modelDetails"' in html
    assert 'id="diagramTab"' in html
    assert 'data-tab="diagram"' in html


def test_three_docked_panels_keep_window_controls_and_single_output_toggle():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert html.count('data-panel-action="dock"') == 3
    assert html.count('data-panel-action="minimize"') == 3
    assert html.count('data-panel-action="maximize"') == 3
    assert html.count('data-panel-action="close"') == 3
    assert html.count('data-panel-toggle=') == 3


def test_output_views_split_into_independent_browser_windows_only_when_undocked():
    script = Path('static/workspace_layout.js').read_text(encoding='utf-8')
    css = Path('static/workspace_layout.css').read_text(encoding='utf-8')
    assert "const outputViewNames = ['text', 'sysml', 'diagram', 'details']" in script
    assert 'outputPopups = new Map()' in script
    assert 'outputPopupMonitors = new Map()' in script
    assert 'openOutputBrowserWindow' in script
    assert 'redockOutputView' in script
    assert "url.searchParams.set('detachedPanel', name)" in script
    assert 'window.open' in script
    assert 'mbse-redock-output-view' in script
    assert 'mbse-output-window-closed' in script
    assert 'requestFullscreen' in script
    assert 'body.detached-output-window' in css
    assert '.output-tab-button.is-detached-view' in css


def test_output_sidebar_can_be_hidden_without_closing_detached_views():
    script = Path('static/workspace_layout.js').read_text(encoding='utf-8')
    assert "function setPanelVisible(name, visible)" in script
    assert "panel.hidden = !visible" in script
    set_visible = script.split('function setPanelVisible(name, visible)', 1)[1].split('function requestRedockFromDetachedWindow', 1)[0]
    assert 'popup.close()' not in set_visible
    assert 'outputPopups.clear' not in set_visible
    assert 'All output views are undocked.' in Path('templates/index.html').read_text(encoding='utf-8')


def test_single_right_output_splitter_resizes_combined_sidebar():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    script = Path('static/workspace_layout.js').read_text(encoding='utf-8')
    css = Path('static/workspace_layout.css').read_text(encoding='utf-8')
    assert 'data-splitter="output"' in html
    assert 'data-splitter="text"' not in html
    assert 'data-splitter="sysml"' not in html
    assert "--output-width" in script
    assert "--output-width" in css
    assert "installSplitter(splitters.output, '--output-width', 'output', 300, 820, 'right')" in script


def test_splitter_directions_match_left_completion_and_right_output_sidebar():
    script = Path('static/workspace_layout.js').read_text(encoding='utf-8')
    assert "direction === 'left' ? startWidth + delta : startWidth - delta" in script
    assert "installSplitter(splitters.completion, '--completion-width', 'completion', 190, 520, 'left')" in script
    assert "installSplitter(splitters.output, '--output-width', 'output', 300, 820, 'right')" in script


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
