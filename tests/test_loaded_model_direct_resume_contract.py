from pathlib import Path


def test_loaded_model_opens_directly_on_refinement_loop_without_gap_review():
    source = Path('loaded_model_direct_resume.py').read_text(encoding='utf-8')
    assert 'self._run_loaded_refinement_loop()' in source
    assert 'self._review_loaded_gaps()' not in source
    assert '("check",' not in source
    assert '("finish",' not in source


def test_loaded_model_user_vocabulary_is_configured_outside_refinement_logic():
    source = Path('loaded_model_direct_resume.py').read_text(encoding='utf-8')
    guidance = Path('ui_guidance.json').read_text(encoding='utf-8')
    assert 'configured_choices' in source
    assert 'configured_text' in source
    assert '"loaded_model"' in guidance
    expected_labels = [
        'Goals',
        'People, organizations, places, or systems involved',
        'Activities',
        'Information or material exchanged',
        'Means of communication',
        'Characteristics and limits',
    ]
    for label in expected_labels:
        assert label in guidance
        assert label not in source
    assert 'Operational Capability' not in source
    assert 'Operational Entity' not in source
    assert 'Operational Actor' not in source
    assert 'Operational Exchange' not in source
    assert 'Communication Mean' not in source


def test_loaded_model_asks_intent_before_model_category():
    source = Path('loaded_model_direct_resume.py').read_text(encoding='utf-8')
    loop = source.split('def _run_loaded_refinement_loop', 1)[1]
    mode_index = loop.index('mode = self._loaded_change_mode()')
    category_index = loop.index('category = self._loaded_refinement_menu()')
    assert mode_index < category_index
    assert 'self._loaded_ui_choices("intents", self._LOADED_INTENTS)' in source
    assert 'self._loaded_ui_choices("categories", self._LOADED_CATEGORIES)' in source


def test_loaded_participant_add_reuses_normal_creation_and_classification_flow():
    source = Path('loaded_model_direct_resume.py').read_text(encoding='utf-8')
    assert 'participant_id = self.ask_additional_participant()' in source
    assert 'self.capture_actions_for_participant(participant_id)' in source
    assert 'classification_source="user_selected_concept"' not in source


def test_loaded_characteristics_reuse_existing_builder_storage_and_add_edit_routes():
    source = Path('loaded_model_direct_resume.py').read_text(encoding='utf-8')
    assert '"characteristics"' in source
    assert 'self._characteristic_targets()' in source
    assert 'self._build_characteristic()' in source
    assert 'self._store_characteristic(target, characteristic)' in source
    assert 'replace_characteristic' in source
    assert 'replace_exchange_characteristic' in source


def test_loaded_model_uses_targeted_interaction_communication_flow():
    source = Path('loaded_model_direct_resume.py').read_text(encoding='utf-8')
    assert 'def _capture_communication_for_exchange(' in source
    assert 'self.capture_communication_for_exchange(' in source
    assert 'def _work_on_loaded_communication(' in source
    assert 'BaseOAApp.capture_communication' not in source


def test_resume_worker_uses_direct_loaded_model_flow_before_base_loaded_flow():
    source = Path('web_worker_resume.py').read_text(encoding='utf-8')
    direct = source.index('DirectLoadedModelResumeMixin,')
    base = source.index('LoadedModelFlowMixin,')
    assert direct < base
