(() => {
  if (window.__mbseChangeImpactPresentationInstalled) return;
  window.__mbseChangeImpactPresentationInstalled = true;

  let latestModel = {};

  function entries(presentation, key) {
    return Array.isArray(presentation?.[key])
      ? presentation[key].filter(item => item && typeof item === 'object')
      : [];
  }

  function namesFor(items, {previewCurrentName = false} = {}) {
    return items
      .map(item => String(previewCurrentName ? (item.old_name || item.name || '') : (item.name || '')).trim())
      .filter(Boolean)
      .sort((a, b) => b.length - a.length);
  }

  function textMatches(text, names) {
    const value = String(text || '').toLocaleLowerCase();
    return names.some(name => value.includes(name.toLocaleLowerCase()));
  }

  function scenarioImpacts(model, modified) {
    const ids = new Set(modified.map(item => String(item.id || '')).filter(Boolean));
    if (!ids.size) return [];
    return (Array.isArray(model?.scenarios) ? model.scenarios : [])
      .filter(scenario => Array.isArray(scenario?.steps) && scenario.steps.some(step => {
        if (!step || typeof step !== 'object') return false;
        if (ids.has(String(step.activity_id || ''))) return true;
        if (ids.has(String(step.source_activity_id || ''))) return true;
        if (ids.has(String(step.target_activity_id || ''))) return true;
        const communication = step.communication_mean;
        return communication && typeof communication === 'object' && (
          ids.has(String(communication.source_participant_id || '')) ||
          ids.has(String(communication.target_participant_id || ''))
        );
      }))
      .map(scenario => ({
        kind: 'scenario',
        id: String(scenario.id || ''),
        name: String(scenario.name || scenario.id || 'Operational Scenario'),
        type: 'OperationalScenario',
      }));
  }

  function clearDomHighlights() {
    document.querySelectorAll('.mbse-change-modified, .mbse-change-impacted')
      .forEach(node => node.classList.remove('mbse-change-modified', 'mbse-change-impacted'));
    document.querySelectorAll('.mbse-change-summary').forEach(node => node.remove());
  }

  function applyTextualHighlights(modifiedNames, impactedNames) {
    const selectors = [
      '#modelTextual .tree-item-name',
      '#modelTextual .tree-line',
      '#modelDetails .detail-name',
      '#modelDetails .detail-value',
    ];
    document.querySelectorAll(selectors.join(',')).forEach(node => {
      if (textMatches(node.textContent, modifiedNames)) {
        node.classList.add('mbse-change-modified');
      } else if (textMatches(node.textContent, impactedNames)) {
        node.classList.add('mbse-change-impacted');
      }
    });
  }

  function appendCodeLine(code, text, className = '') {
    const line = document.createElement('span');
    line.className = `mbse-change-line ${className}`.trim();
    line.textContent = text || ' ';
    code.appendChild(line);
    code.appendChild(document.createTextNode('\n'));
  }

  function applySysmlHighlights(modifiedNames, impactedNames) {
    const code = document.querySelector('#utilitySysmlView code');
    if (!code) return;
    const raw = String(code.textContent || '').replace(/\n$/, '');
    const lines = raw.split('\n');
    code.textContent = '';
    lines.forEach(line => {
      if (textMatches(line, modifiedNames)) {
        appendCodeLine(code, line, 'mbse-change-modified');
      } else if (textMatches(line, impactedNames)) {
        appendCodeLine(code, line, 'mbse-change-impacted');
      } else {
        appendCodeLine(code, line);
      }
    });
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(String(value));
    return String(value).replace(/["\\]/g, '\\$&');
  }

  function applyDiagramHighlights(modified, impacted, relations) {
    modified.forEach(item => {
      const node = document.querySelector(`[data-node-id="${cssEscape(item.id)}"]`);
      if (node) node.classList.add('mbse-change-modified');
    });
    impacted.forEach(item => {
      const node = document.querySelector(`[data-node-id="${cssEscape(item.id)}"]`);
      if (node && !node.classList.contains('mbse-change-modified')) {
        node.classList.add('mbse-change-impacted');
      }
    });
    relations.forEach(item => {
      document.querySelectorAll(`[data-edge-id="${cssEscape(item.id)}"]`).forEach(edge => {
        edge.classList.add('mbse-change-impacted');
      });
    });
  }

  function insertSummary(container, text, before = null) {
    if (!container || !text) return;
    const note = document.createElement('div');
    note.className = 'mbse-change-summary modified';
    note.textContent = text;
    if (before) container.insertBefore(note, before);
    else container.prepend(note);
  }

  function addChangeSummary(presentation) {
    const modified = entries(presentation, 'modified');
    if (!modified.length) return;
    const item = modified[0];
    let text = '';
    if (presentation?.operation === 'rename_preview') {
      text = `Proposed rename — ${String(item.old_name || item.id || 'item')} → ${String(item.name || '')}. No model change has been committed yet.`;
    } else if (presentation?.operation === 'delete_preview') {
      text = `Proposed delete — ${String(item.name || item.id || 'model element')}. No model change has been committed yet.`;
    } else if (presentation?.operation === 'delete') {
      text = `Deleted: ${String(item.name || item.id || 'model element')}`;
    }
    if (!text) return;

    insertSummary(document.getElementById('modelTextual'), text);
    const sysmlContainer = document.querySelector('#utilitySysmlView .sysml-text-placeholder');
    if (sysmlContainer) {
      insertSummary(sysmlContainer, text, sysmlContainer.querySelector('pre'));
    }
  }

  function apply(model = latestModel) {
    latestModel = model || {};
    const presentation = latestModel?.presentation || {};
    const modified = entries(presentation, 'modified');
    const impacted = entries(presentation, 'impacted');
    const impactedRelations = entries(presentation, 'impacted_relations');
    const impactedScenarios = scenarioImpacts(latestModel, modified);

    clearDomHighlights();
    if (!modified.length && !impacted.length && !impactedRelations.length) return;

    const preview = presentation?.operation === 'rename_preview';
    const modifiedNames = namesFor(modified, {previewCurrentName: preview});
    const impactedNames = namesFor([...impacted, ...impactedRelations, ...impactedScenarios]);
    applyTextualHighlights(modifiedNames, impactedNames);
    applySysmlHighlights(modifiedNames, impactedNames);
    applyDiagramHighlights(modified, impacted, impactedRelations);
    addChangeSummary(presentation);
  }

  function schedule(model) {
    latestModel = model || latestModel || {};
    window.requestAnimationFrame(() => apply(latestModel));
  }

  const baseApplyState = window.applyState;
  if (typeof baseApplyState === 'function') {
    window.applyState = function changeImpactAwareApplyState(state) {
      baseApplyState(state);
      schedule(state?.model || {});
    };
  }

  window.addEventListener('mbse:model-projections-updated', event => {
    schedule(event.detail?.model || latestModel);
  });
})();
