from pathlib import Path

from composition_flow import CompositionFlowMixin
from graph_model import OAGraph
from participant_composition import (
    OperationalActorCompositionFlowMixin,
    install_operational_actor_composition_support,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
MODEL_FILES = (ROOT / "static" / "model_file_io.js").read_text(encoding="utf-8")
OA_HELP = (ROOT / "static" / "oa_header_help.js").read_text(encoding="utf-8")


def _add(graph: OAGraph, node_type: str, name: str) -> str:
    ok, node_id, error = graph.add_node(node_type, name)
    assert ok, error
    return node_id


def test_diagram_integration_preserves_loaded_model_ui_contract():
    assert 'id="saveModelButton"' in TEMPLATE
    assert 'id="loadModelButton"' in TEMPLATE
    assert 'model_file_io.js' in TEMPLATE
    assert '/api/model/export' in MODEL_FILES
    assert '/api/model/load' in MODEL_FILES


def test_diagram_integration_preserves_compact_oa_help_popover():
    assert 'id="oaInfoButton"' in TEMPLATE
    assert 'id="oaInfoPopover"' in TEMPLATE
    assert 'role="tooltip" hidden' in TEMPLATE
    assert 'Purpose' in TEMPLATE
    assert 'Objective' in TEMPLATE
    assert 'Key question' in TEMPLATE
    assert "popover.hidden = false" in OA_HELP
    assert "popover.hidden = true" in OA_HELP


def test_actor_is_available_as_a_composition_parent_in_guided_flow():
    install_operational_actor_composition_support()

    class Flow(OperationalActorCompositionFlowMixin, CompositionFlowMixin):
        def __init__(self):
            self.model = OAGraph()
            self.actor = _add(self.model, "OperationalActor", "Lead role")
            self.called_parent = None
            self.answers = iter([True, False, False])

        def ask_yes_no(self, *_args, **_kwargs):
            return next(self.answers)

        def ask_choice(self, *_args, **_kwargs):
            return self.actor

        def _add_participant_child(self, parent_id: str) -> None:
            self.called_parent = parent_id

    flow = Flow()
    targets = dict(flow._decomposition_targets())
    assert flow.actor in targets
    flow.capture_decomposition()
    assert flow.called_parent == flow.actor
