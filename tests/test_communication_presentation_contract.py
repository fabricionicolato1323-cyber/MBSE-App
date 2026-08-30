from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_communication_presentation_assets_are_loaded_after_generic_projection_sync():
    loader = (ROOT / "static" / "model_relationships.js").read_text(encoding="utf-8")
    assert "model_projection_sync.js" in loader
    assert "data-model-projection-sync-script" in loader
    assert "loadOutputRenderers" in loader
    assert "communication_presentation.js" in loader
    assert "communication_presentation.css" in loader
    assert "oaCommunicationPresentationScript" in loader


def test_generic_projection_sync_uses_complete_model_content_not_field_allow_list():
    script = (ROOT / "static" / "model_projection_sync.js").read_text(encoding="utf-8")
    assert "canonicalValue" in script
    assert "canonicalCollection(model?.nodes)" in script
    assert "canonicalCollection(model?.drafts)" in script
    assert "canonicalCollection(model?.edges)" in script
    assert "mbse:model-projections-updated" in script
    assert "register('pseudo-code'" in script
    assert "register('details'" in script
    assert "projectionSynchronizedApplyState" in script


def test_generic_projection_sync_is_the_single_owner_after_it_loads():
    interaction = (ROOT / "static" / "revision_interaction.js").read_text(encoding="utf-8")
    assert "if (!window.mbseModelProjectionSync)" in interaction
    guarded_block = interaction.split("if (!window.mbseModelProjectionSync)", 1)[1]
    assert "renderRevisionTextualModel(state.model || {})" in guarded_block
    assert "renderRevisionDetails(state.model || {})" in guarded_block


def test_textual_communication_is_a_hierarchy_with_explicit_carried_exchanges():
    script = (ROOT / "static" / "communication_presentation.js").read_text(encoding="utf-8")
    style = (ROOT / "static" / "communication_presentation.css").read_text(encoding="utf-8")
    assert "COMMUNICATION_MEAN" in script
    assert "exchange_refs" in script
    assert "revisionTreeItem(clean(edge.name) || 'Communication method')" in script
    assert "↔" in script
    assert "exchangeLine(ref, byId)" in script
    assert "No interaction explicitly assigned" in script
    assert ".tree-line.communication-carried-exchange" in style
    assert "margin-left: 18px" in style
    assert "border-left: 1px solid" in style


def test_pseudo_code_exchanges_show_live_communication_assignment():
    renderer = (ROOT / "static" / "revision_model.js").read_text(encoding="utf-8")
    presentation = (ROOT / "static" / "communication_presentation.js").read_text(encoding="utf-8")
    assert "operational-exchange-tree-item" in renderer
    assert "dataset.exchangeSource" in renderer
    assert "dataset.exchangeTarget" in renderer
    assert "dataset.exchangeName" in renderer
    assert "communicationAssignmentsByExchange" in presentation
    assert "Communication: Unassigned" in presentation
    assert "Communication: ${names.join(', ')}" in presentation
    assert "exchange-communication-line" in presentation
    assert "mbse:model-projections-updated" in presentation


def test_diagram_communication_label_shows_mean_endpoints_and_exchange_names():
    script = (ROOT / "static" / "communication_presentation.js").read_text(encoding="utf-8")
    style = (ROOT / "static" / "communication_presentation.css").read_text(encoding="utf-8")
    assert ".communication-label[data-edge-id]" in script
    assert "communication-name-line" in script
    assert "communication-endpoints-line" in script
    assert "communication-exchange-line" in script
    assert "refs.slice(0, 3)" in script
    assert ".communication-name-line" in style
    assert ".communication-endpoints-line" in style
    assert ".communication-exchange-line" in style
