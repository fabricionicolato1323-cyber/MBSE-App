from pathlib import Path


def test_operational_analysis_guidance_is_compact_hover_or_click_help():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    script = Path('static/oa_header_help.js').read_text(encoding='utf-8')
    assert 'id="oaInfoButton"' in html
    assert 'id="oaInfoPopover"' in html
    assert '<strong>Purpose</strong>' in html
    assert '<strong>Objective</strong>' in html
    assert '<strong>Key question</strong>' in html
    assert 'class="oa-brief"' not in html
    assert "mouseenter" in script
    assert "aria-expanded" in script


def test_large_model_choices_use_searchable_hierarchical_picker():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    script = Path('static/searchable_choice_picker.js').read_text(encoding='utf-8')
    css = Path('static/searchable_choice_picker.css').read_text(encoding='utf-8')
    assert 'searchable_choice_picker.js' in html
    assert "SEARCHABLE_CHOICE_MINIMUM = 6" in script
    assert "search.type = 'search'" in script
    assert 'Search model items' in script
    assert "'Actions'" in script
    assert "'Participants / Context'" in script
    assert "'Goals'" in script
    assert '.choice-picker-menu' in css
    assert '.choice-picker-group' in css


def test_post_pass_refinement_starts_from_existing_model_selection():
    flow = Path('focused_refinement.py').read_text(encoding='utf-8')
    worker = Path('web_worker.py').read_text(encoding='utf-8')
    assert 'FocusedRefinementMixin' in worker
    assert 'Which participant or action would you like to work on?' in flow
    assert 'Which action should the interaction start from?' in flow
    assert 'Action:' in flow
    assert 'Participant / context' in flow
    assert '_capture_interactions_for_source' in flow
    assert '_capture_characteristics_for_action' in flow
