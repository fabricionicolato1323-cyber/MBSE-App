from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_completion_absorbs_activity_to_goal_model_check():
    source = (ROOT / "static" / "completion_continuous_check.js").read_text(encoding="utf-8")
    assert "SUPPORTS_CAPABILITY" in source
    assert "goalLinkedActions" in source
    assert "goalLinkRatio" in source
    assert ".5 + .5 * goalLinkRatio" in source
    assert "connected to an operational goal" in source


def test_completion_patch_preserves_existing_seven_area_coverage():
    source = (ROOT / "static" / "completion_continuous_check.js").read_text(encoding="utf-8")
    labels = [
        "Operational goal",
        "Participants / context",
        "Operational activities",
        "Activity ownership",
        "Operational interactions",
        "Communication means",
        "Characteristics / limits",
    ]
    for label in labels:
        assert label in source
    for weight in ("weight: 15", "weight: 20", "weight: 10"):
        assert weight in source


def test_completion_patch_wraps_live_state_rendering():
    source = (ROOT / "static" / "completion_continuous_check.js").read_text(encoding="utf-8")
    assert "continuousCompletionApplyState" in source
    assert "renderContinuousCompletion(state?.model || {})" in source
    assert "dataset.continuousCheck" in source


def test_relationship_loader_installs_completion_patch_after_workspace_initialization():
    loader = (ROOT / "static" / "model_relationships.js").read_text(encoding="utf-8")
    assert "completion_continuous_check.js" in loader
    assert "ensureCompletionPatch" in loader
    assert "window.addEventListener('load', load" in loader
