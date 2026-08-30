// Operational Scenario projection fixes.
//
// 1. NetworkX MultiDiGraph edge keys are only unique for one source/target pair.
//    The diagram previously used edge.key alone as a visual identity, so several
//    unrelated exchanges could all become "edge:0" and highlight together.
//    Give every projected edge a deterministic, globally unique browser id before
//    the diagram and scenario renderers see the model.
// 2. Keep scenarios saved by the first implementation compatible by resolving
//    their interaction step edge_id from source/target/key/name on every projection.
// 3. When a saved scenario is active, de-emphasize unrelated Activities and
//    Operational Interactions to 70% opacity (30% reduction) without hiding them.

const clean = value => String(value ?? '').replace(/\s+/g, ' ').trim();

function edgeDiscriminator(edge, index) {
  if (edge?.key !== undefined && edge?.key !== null && String(edge.key) !== '') {
    return `key:${String(edge.key)}`;
  }
  const name = clean(edge?.name);
  return name ? `name:${name}` : `index:${index}`;
}

function projectedEdgeId(edge, index) {
  const existing = clean(edge?.id);
  if (existing) return existing;

  const parts = [
    clean(edge?.type) || 'EDGE',
    clean(edge?.source) || 'source',
    clean(edge?.target) || 'target',
    edgeDiscriminator(edge, index),
  ];
  return `oa-edge:${parts.map(part => encodeURIComponent(part)).join(':')}`;
}

function interactionMatchesStep(edge, step) {
  if (!edge || edge.type !== 'OPERATIONAL_EXCHANGE' || !step) return false;
  if (edge.source !== step.source_activity_id || edge.target !== step.target_activity_id) {
    return false;
  }

  if (step.edge_key !== undefined && step.edge_key !== null && String(step.edge_key) !== '') {
    return String(edge.key) === String(step.edge_key);
  }

  const wantedName = clean(step.exchange_name);
  return !wantedName || clean(edge.name) === wantedName;
}

function normalizeOperationalScenarioProjection(model) {
  if (!model || typeof model !== 'object') return model;

  const edges = Array.isArray(model.edges) ? model.edges : [];
  edges.forEach((edge, index) => {
    if (!edge || typeof edge !== 'object') return;
    if (!clean(edge.id)) edge.id = projectedEdgeId(edge, index);
  });

  const exchanges = edges.filter(edge => edge?.type === 'OPERATIONAL_EXCHANGE');
  const scenarios = Array.isArray(model.scenarios) ? model.scenarios : [];
  scenarios.forEach(scenario => {
    if (!scenario || !Array.isArray(scenario.steps)) return;
    scenario.steps.forEach(step => {
      if (!step || step.kind !== 'interaction') return;
      const match = exchanges.find(edge => interactionMatchesStep(edge, step));
      if (match?.id) step.edge_id = match.id;
    });
  });

  return model;
}

function installProjectionNormalizer() {
  const priorApplyState = window.applyState;
  if (typeof priorApplyState !== 'function') return;
  if (priorApplyState.__oaScenarioEdgeIdentityNormalized) return;

  const wrapped = function operationalScenarioIdentityApplyState(nextState) {
    normalizeOperationalScenarioProjection(nextState?.model);
    return priorApplyState(nextState);
  };
  wrapped.__oaScenarioEdgeIdentityNormalized = true;
  window.applyState = wrapped;
}

function installScenarioFocusStyle() {
  if (document.getElementById('oaScenarioFocusStyle')) return;
  const style = document.createElement('style');
  style.id = 'oaScenarioFocusStyle';
  style.textContent = `
    /* A saved Operational Scenario uses scenario-mode while its authoring bar is
       hidden. Keep the complete OA visible, but reduce unrelated Activities and
       Interactions by exactly 30% (70% opacity). */
    #diagramTab.scenario-mode:not(.oa-scenario-authoring-active)
      .oa-diagram-node.type-operationalactivity:not(.selected),
    #diagramTab.scenario-mode:not(.oa-scenario-authoring-active)
      .oa-diagram-edge.operational-exchange:not(.selected),
    #diagramTab.scenario-mode:not(.oa-scenario-authoring-active)
      .oa-diagram-edge-label.interaction-label:not(.selected) {
      opacity: .70 !important;
      transition: opacity 140ms ease;
    }

    #diagramTab.scenario-mode:not(.oa-scenario-authoring-active)
      .oa-diagram-node.type-operationalactivity.selected,
    #diagramTab.scenario-mode:not(.oa-scenario-authoring-active)
      .oa-diagram-edge.operational-exchange.selected,
    #diagramTab.scenario-mode:not(.oa-scenario-authoring-active)
      .oa-diagram-edge-label.interaction-label.selected {
      opacity: 1 !important;
    }
  `;
  document.head.appendChild(style);
}

installProjectionNormalizer();
installScenarioFocusStyle();

export {normalizeOperationalScenarioProjection, projectedEdgeId};
