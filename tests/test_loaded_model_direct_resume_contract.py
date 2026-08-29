from pathlib import Path


def test_loaded_model_skips_redundant_edit_confirmation():
    source = Path('loaded_model_direct_resume.py').read_text(encoding='utf-8')
    assert 'self._review_loaded_gaps()' in source
    assert 'self._run_loaded_refinement_loop()' in source
    assert 'ask_yes_no(' not in source


def test_resume_worker_uses_direct_loaded_model_flow_before_base_loaded_flow():
    source = Path('web_worker_resume.py').read_text(encoding='utf-8')
    direct = source.index('DirectLoadedModelResumeMixin,')
    base = source.index('LoadedModelFlowMixin,')
    assert direct < base
