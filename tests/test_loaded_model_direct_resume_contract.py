from pathlib import Path


def test_loaded_model_opens_directly_on_concept_menu_without_gap_review():
    source = Path('loaded_model_direct_resume.py').read_text(encoding='utf-8')
    assert 'self._run_loaded_refinement_loop()' in source
    assert 'self._review_loaded_gaps()' not in source
    assert 'What would you like to change in the loaded model?' in source


def test_loaded_model_menu_contains_only_supported_oa_concepts():
    source = Path('loaded_model_direct_resume.py').read_text(encoding='utf-8')
    expected = [
        'Operational Capability',
        'Operational Entity',
        'Operational Actor',
        'Operational Activity',
        'Operational Exchange',
        'Communication Mean',
    ]
    for label in expected:
        assert label in source
    assert '("check",' not in source
    assert '("finish",' not in source


def test_loaded_model_asks_modify_existing_or_add_new_after_concept_choice():
    source = Path('loaded_model_direct_resume.py').read_text(encoding='utf-8')
    assert '"What would you like to do?"' in source
    assert '("modify", "Modify existing")' in source
    assert '("add", "Add new")' in source
    assert 'self._run_loaded_concept_action(concept, mode)' in source


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
