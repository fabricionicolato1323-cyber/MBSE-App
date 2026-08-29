from pathlib import Path


def test_loaded_model_menu_exposes_explicit_new_concept_paths():
    source = Path('loaded_model_flow.py').read_text(encoding='utf-8')
    assert 'What would you like to change in the loaded model?' in source
    assert '("new_goal", "Add new goal")' in source
    assert '("new_participant", "Add new participant / context")' in source
    assert '("new_action", "Add new action")' in source
    assert '("participants", "Refine existing participants and actions")' in source


def test_new_loaded_action_immediately_checks_optional_relationships():
    source = Path('loaded_model_flow.py').read_text(encoding='utf-8')
    assert 'def create_activity_from_frame(' in source
    assert '_continue_from_new_action(action_id)' in source
    assert 'Would you like to connect' in source
    assert 'through an interaction?' in source
    assert 'This action sends or provides something to another action' in source
    assert 'Another action sends or provides something to this action' in source
    assert '_capture_communication_for_exchange' in source


def test_new_loaded_participant_and_goal_continue_into_relationship_questions():
    source = Path('loaded_model_flow.py').read_text(encoding='utf-8')
    assert 'def _continue_from_new_participant(' in source
    assert 'capture_actions_for_participant(participant_id)' in source
    assert 'part of another group, organization, facility, or larger element' in source
    assert 'operate in or inside a place or area' in source
    assert 'def _continue_from_new_goal(' in source
    assert 'Does an existing action contribute to' in source


def test_loaded_refinement_loop_restarts_after_each_change():
    source = Path('loaded_model_flow.py').read_text(encoding='utf-8')
    assert 'choice = self._loaded_refinement_menu()' in source
    assert 'self._create_loaded_goal()' in source
    assert 'self._create_loaded_participant()' in source
    assert 'self._create_new_action_reference()' in source
