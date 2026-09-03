from __future__ import annotations

import sys
from pathlib import Path

import app_base as _base
from app_base import *  # noqa: F401,F403 - preserve the public surface of app.py
from capability_flow import CapabilityStructuralFlowMixin
from change_impact_finalize import install_change_impact_finalize_support
from change_impact_refinement import install_change_impact_refinement_support
from characteristic_edit import install_characteristic_edit_support
from characteristic_operators import install_characteristic_operator_support
from characteristics_flow import CharacteristicsFlowMixin
from communication_exchange_link import CommunicationExchangeLinkFlowMixin
from composition_flow import CompositionFlowMixin
from conversational_surface import ConversationalSurfaceMixin
from guidance_flow import GuidanceFlowMixin
from knowledge_graph_role_boundary import install_role_boundary_knowledge_support
from knowledge_graph_structural_input import install_structural_input_knowledge_support
from llm_conversation import install_conversational_llm_support
from minimal_input_policy import MinimalInputPolicyMixin
from minimal_input_web_patch import install_minimal_web_input_policy
from next_best_question_flow import install_next_best_question_support
from participant_classification_simple import SimplifiedParticipantClassificationMixin
from participant_composition import (
    OperationalActorCompositionFlowMixin,
    install_operational_actor_composition_support,
)
from participant_flow import ParticipantFlowMixin


# Extend the central graph, Knowledge Graph, and local LLM client before any OAApp
# instance is created. Structural input semantics stay in the KG; the LLM remains
# presentation-only and receives only an already-decided question to rephrase.
install_role_boundary_knowledge_support()
install_structural_input_knowledge_support()
install_conversational_llm_support()
install_operational_actor_composition_support()
install_characteristic_operator_support()
install_characteristic_edit_support()
install_change_impact_refinement_support()
install_change_impact_finalize_support()
install_minimal_web_input_policy()

# The adaptive question engine changes only the Web guided lifecycle. web_worker.py
# imports this module after its own process has started, so the process entry point
# is a stable boundary that avoids changing terminal behavior or import-only tests.
if Path(sys.argv[0]).name.casefold() == "web_worker.py":
    install_next_best_question_support()


class OAApp(
    CapabilityStructuralFlowMixin,
    ConversationalSurfaceMixin,
    GuidanceFlowMixin,
    MinimalInputPolicyMixin,
    SimplifiedParticipantClassificationMixin,
    ParticipantFlowMixin,
    OperationalActorCompositionFlowMixin,
    CompositionFlowMixin,
    CommunicationExchangeLinkFlowMixin,
    CharacteristicsFlowMixin,
    _base.OAApp,
):
    """Guided builder with KG-led semantics and optional conversational phrasing."""

    def capture_structure_and_environment(self) -> None:
        super().capture_structure_and_environment()
        self.capture_decomposition()

    def capture_communication(self) -> None:
        super().capture_communication()
        self.capture_characteristics()


# app_base.main resolves OAApp from its own module globals. Rebinding preserves
# the established entry point while making it instantiate the extended class.
_base.OAApp = OAApp
main = _base.main


if __name__ == "__main__":
    main()
