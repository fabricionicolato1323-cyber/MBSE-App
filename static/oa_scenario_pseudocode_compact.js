(() => {
  if (window.__oaCompactScenarioPseudoCodeInstalled) return;
  window.__oaCompactScenarioPseudoCodeInstalled = true;

  let scheduled = false;
  let observer = null;

  const clean = value => String(value ?? '').replace(/\s+/g, ' ').trim();

  function latestModel() {
    return window.mbseModelProjectionSync?.getLatest?.().model || null;
  }

  function scenarioLines(scenario, nodes) {
    const scenarioName = clean(scenario?.name || scenario?.id || 'Scenario');
    const lines = [`scenario "${scenarioName}"`];
    const steps = Array.isArray(scenario?.steps) ? scenario.steps : [];
    const firstActivity = steps.find(step => step?.kind === 'activity');

    if (firstActivity?.activity_id) {
      let chain = clean(
        nodes.get(firstActivity.activity_id)?.name || firstActivity.activity_id
      );

      steps
        .filter(step => step?.kind === 'interaction')
        .forEach(step => {
          const exchange = clean(step.exchange_name) || 'Interaction';
          const target = clean(
            nodes.get(step.target_activity_id)?.name || step.target_activity_id
          );
          chain += ` -- "${exchange}" --> ${target}`;
        });

      if (chain) lines.push(chain);
    }

    if (scenario?.valid === false) {
      lines.push('// INVALID: one or more referenced model elements no longer exist');
    }
    return lines;
  }

  function applyCompactScenarioPseudoCode() {
    scheduled = false;
    const root = document.getElementById('modelTextual');
    const section = root?.querySelector('.operational-scenarios-section');
    const model = latestModel();
    const scenarios = Array.isArray(model?.scenarios) ? model.scenarios : [];
    if (!section || !scenarios.length) return;

    const nodes = new Map((model.nodes || []).map(node => [node.id, node]));
    const items = [...section.querySelectorAll('.oa-scenario-text-item')];

    items.forEach((item, index) => {
      const scenario = scenarios[index];
      const code = item.querySelector('.oa-scenario-pseudocode');
      if (!scenario || !code) return;
      const compact = scenarioLines(scenario, nodes).join('\n');
      if (code.textContent !== compact) code.textContent = compact;
    });
  }

  function scheduleCompactRender() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(applyCompactScenarioPseudoCode);
  }

  function installObserver() {
    const root = document.getElementById('modelTextual');
    if (!root) {
      requestAnimationFrame(installObserver);
      return;
    }
    observer?.disconnect();
    observer = new MutationObserver(scheduleCompactRender);
    observer.observe(root, {childList: true, subtree: true});
    scheduleCompactRender();
  }

  if (!document.getElementById('oaCompactScenarioPseudoCodeStyle')) {
    const style = document.createElement('style');
    style.id = 'oaCompactScenarioPseudoCodeStyle';
    style.textContent = `
      .oa-scenario-pseudocode {
        white-space: pre-wrap !important;
        overflow-x: hidden !important;
        overflow-wrap: anywhere;
        word-break: normal;
      }
    `;
    document.head.appendChild(style);
  }

  window.addEventListener('mbse:model-projections-updated', scheduleCompactRender);
  installObserver();
})();
