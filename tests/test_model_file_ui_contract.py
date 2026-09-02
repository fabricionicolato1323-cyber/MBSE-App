from pathlib import Path


def test_header_is_compact_and_sequence_word_is_removed():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert '>Arcadia viewpoint</div>' in html
    assert 'Arcadia viewpoint sequence' not in html


def test_save_and_load_controls_are_present():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert 'id="saveModelButton"' in html
    assert 'id="loadModelButton"' in html
    assert 'id="loadModelInput"' in html
    assert 'id="saveModelModal"' in html
    assert 'id="modelNameInput"' in html
    assert 'model_file_io.js' in html


def test_save_uses_native_location_picker_with_download_fallback():
    script = Path('static/model_file_io.js').read_text(encoding='utf-8')
    assert 'showSaveFilePicker' in script
    assert 'createWritable' in script
    assert 'Search' not in script
    assert 'anchor.download' in script


def test_loaded_model_flow_resumes_from_model_gaps():
    script = Path('loaded_model_flow.py').read_text(encoding='utf-8')
    assert '_first_loaded_gap' in script
    assert 'has no operational goal' in script
    assert 'has no action' in script
    assert 'has no confirmed performer' in script
    assert 'is not connected to a goal' in script
    assert 'Would you like to address this now?' in script
