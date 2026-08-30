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


def test_default_layout_is_completion_conversation_pseudocode_then_sysml():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    completion_index = html.index('id="completionPanel"')
    chat_index = html.index('id="chatPanel"')
    text_index = html.index('id="modelPanel"')
    sysml_index = html.index('id="sysmlPanel"')
    assert completion_index < chat_index < text_index < sysml_index
    assert 'id="completionPercent"' in html
    assert 'id="completionList"' in html
    assert 'data-panel-toggle="text">Pseudo-code</button>' in html
    assert 'data-panel-toggle="sysml">SysML V2</button>' in html


def test_pseudocode_and_sysml_are_independent_workspace_panels():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert 'data-panel="text" data-output-panel="text"' in html
    assert 'data-panel="sysml" data-output-panel="sysml"' in html
    assert '<h2>Pseudo-code</h2>' in html
    assert '<h2>SysML V2</h2>' in html
    assert 'id="utilityTextView"' in html
    assert 'id="utilitySysmlView"' in html
    assert 'data-utility-tab="text"' not in html
    assert 'data-utility-tab="sysml"' not in html
    assert 'SysML V2 textual output' in html
    assert 'intentionally text-based, not a block diagram' in html
    assert 'Generated SysML V2 text will appear here' in html


def test_existing_model_views_remain_available_inside_pseudocode_panel():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert 'data-tab="textual"' in html
    assert 'data-tab="diagram"' in html
    assert 'data-tab="details"' in html
    assert 'id="modelTextual"' in html
    assert 'id="modelDiagram"' in html
    assert 'id="modelDetails"' in html


def test_all_four_panels_keep_dock_minimize_maximize_and_hide_controls():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert html.count('data-panel-action="dock"') == 4
    assert html.count('data-panel-action="minimize"') == 4
    assert html.count('data-panel-action="maximize"') == 4
    assert html.count('data-panel-action="close"') == 4
    assert html.count('data-panel-toggle=') == 4


def test_output_panels_support_independent_browser_windows_and_redocking():
    script = Path('static/workspace_layout.js').read_text(encoding='utf-8')
    css = Path('static/workspace_layout.css').read_text(encoding='utf-8')
    assert "new Set(['text', 'sysml'])" in script
    assert 'outputPopups = new Map()' in script
    assert 'outputPopupMonitors = new Map()' in script
    assert 'openOutputBrowserWindow' in script
    assert 'redockOutputPanel' in script
    assert "url.searchParams.set('detachedPanel', name)" in script
    assert 'window.open' in script
    assert 'mbse-redock-output' in script
    assert 'mbse-output-window-closed' in script
    assert 'requestFullscreen' in script
    assert 'body.detached-output-window' in css
    assert '.detached-target' in css


def test_separate_output_panels_have_independent_resize_widths():
    script = Path('static/workspace_layout.js').read_text(encoding='utf-8')
    css = Path('static/workspace_layout.css').read_text(encoding='utf-8')
    assert "data-splitter=\"text\"" in Path('templates/index.html').read_text(encoding='utf-8')
    assert "data-splitter=\"sysml\"" in Path('templates/index.html').read_text(encoding='utf-8')
    assert "--text-width" in script
    assert "--sysml-width" in script
    assert "--text-width" in css
    assert "--sysml-width" in css
    assert "installSplitter(splitters.text" in script
    assert "installSplitter(splitters.sysml" in script


def test_splitter_directions_match_left_completion_and_right_output_panels():
    script = Path('static/workspace_layout.js').read_text(encoding='utf-8')
    assert "direction === 'left' ? startWidth + delta : startWidth - delta" in script
    assert "installSplitter(splitters.completion, '--completion-width', 'completion', 190, 520, 'left')" in script
    assert "installSplitter(splitters.text, '--text-width', 'text', 280, 760, 'right')" in script
    assert "installSplitter(splitters.sysml, '--sysml-width', 'sysml', 260, 700, 'right')" in script


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
