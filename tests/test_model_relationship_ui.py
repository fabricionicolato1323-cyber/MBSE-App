from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_relationship_renderer_is_loaded_and_derives_required_properties() -> None:
    script = (ROOT / "static" / "model_relationships.js").read_text(encoding="utf-8")
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    assert "LOCATED_IN" in script
    assert "locationTargets" in script
    assert "SUPPORTS_CAPABILITY" in script
    assert "Contributes to" in script
    assert "model_relationships.js" in template


def test_development_assets_are_not_cached() -> None:
    web_app = (ROOT / "web_app.py").read_text(encoding="utf-8")
    assert 'SEND_FILE_MAX_AGE_DEFAULT' in web_app
    assert 'no-store, no-cache' in web_app
