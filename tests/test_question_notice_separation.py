from pathlib import Path


def test_prior_feedback_is_split_from_active_question_card():
    script = Path('static/question_notice_separation.js').read_text(encoding='utf-8')
    assert 'revisionSplitAssistantQuestion' in script
    assert "revisionLineKind(concise) === 'question'" in script
    assert 'notice-row' in script
    assert 'notice-bubble' in script
    assert 'split.notice' in script
    assert 'split.question' in script


def test_notice_presentation_is_loaded_after_main_interaction_renderer():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    interaction_pos = html.index("filename='revision_interaction.js'")
    separation_pos = html.index("filename='question_notice_separation.js'")
    assert separation_pos > interaction_pos
    assert "filename='question_notice_separation.css'" in html


def test_prior_feedback_is_visually_outside_question_card():
    css = Path('static/question_notice_separation.css').read_text(encoding='utf-8')
    assert '.notice-bubble' in css
    assert 'background: transparent' in css
    assert 'border: 0' in css
