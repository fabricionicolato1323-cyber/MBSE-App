from pathlib import Path


def test_choice_help_assets_are_loaded_after_interaction_renderer():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    interaction_index = html.index("filename='revision_interaction.js'")
    help_index = html.index("filename='choice_help.js'")
    assert help_index > interaction_index
    assert "filename='choice_help.css'" in html


def test_choice_lists_get_separate_help_controls_but_binary_choices_do_not():
    script = Path('static/choice_help.js').read_text(encoding='utf-8')
    assert "normalized.choices.forEach(choice =>" in script
    assert "if (normalized.mode === 'choice')" in script
    assert "row.appendChild(revisionCreateChoiceHelpButton(choice))" in script
    assert "event.stopPropagation()" in script


def test_yes_no_question_does_not_show_question_level_help_icon():
    script = Path('static/revision_interaction.js').read_text(encoding='utf-8')
    assert "showQuestionHelp: interaction.mode !== 'yes_no'" in script
    assert "{showHelp: showQuestionHelp}" in script


def test_environmental_participant_has_specific_short_help():
    script = Path('static/choice_help.js').read_text(encoding='utf-8')
    assert "'Environmental participant'" in script
    assert "weather, terrain, water, or wildlife" in script


def test_dynamic_model_choices_have_contextual_fallback_help():
    script = Path('static/choice_help.js').read_text(encoding='utf-8')
    assert "/^Goal:/i" in script
    assert "/^Action:/i" in script
    assert "/^Participant:/i" in script
    assert "/^Interaction:/i" in script


def test_help_is_available_by_hover_focus_and_click_for_lists():
    script = Path('static/choice_help.js').read_text(encoding='utf-8')
    assert "addEventListener('mouseenter'" in script
    assert "addEventListener('focus'" in script
    assert "addEventListener('click'" in script
    assert "aria-expanded" in script
