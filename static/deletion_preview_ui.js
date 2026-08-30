import {projectedEdgeId} from './oa_scenario_projection_fix.js';

const TARGET_CLASS = 'oa-deletion-target';
const IMPACT_CLASS = 'oa-deletion-impact';

function clean(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function canonical(value) {
  return clean(value).toLocaleLowerCase();
}

function stem(value) {
  const text = clean(value)
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '');
  const words = text.match(/[A-Za-z0-9]+/g) || [];
  return words.join('_') || 'element';
}

function activePreview(model) {
  const preview = model?.deletion_preview;
  return preview && preview.active ? preview : null;
}

function installStyle() {
  if (document.getElementById('oaDeletionPreviewStyle')) return;
  const style = document.createElement('style');
  style.id = 'oaDeletionPreviewStyle';
  style.textContent = `
    :root {
      --oa-delete-red: #c73636;
      --oa-delete-red-bg: rgba(199, 54, 54, .10);
      --oa-impact-orange: #d97706;
      --oa-impact-orange-bg: rgba(217, 119, 6, .11);
    }

    .oa-deletion-target {
      color: var(--oa-delete-red) !important;
    }
    .oa-deletion-impact {
      color: var(--oa-impact-orange) !important;
    }

    .oa-diagram-node.oa-deletion-target {
      border-color: var(--oa-delete-red) !important;
      box-shadow: 0 0 0 3px rgba(199, 54, 54, .22) !important;
      background-image: linear-gradient(var(--oa-delete-red-bg), var(--oa-delete-red-bg)) !important;
    }
    .oa-diagram-node.oa-deletion-impact {
      border-color: var(--oa-impact-orange) !important;
      box-shadow: 0 0 0 2px rgba(217, 119, 6, .18) !important;
      background-image: linear-gradient(var(--oa-impact-orange-bg), var(--oa-impact-orange-bg)) !important;
    }
    svg .oa-deletion-target {
      stroke: var(--oa-delete-red) !important;
      fill: var(--oa-delete-red) !important;
      opacity: 1 !important;
    }
    svg path.oa-deletion-target {
      fill: none !important;
      stroke-width: 4px !important;
    }
    svg .oa-deletion-impact {
      stroke: var(--oa-impact-orange) !important;
      fill: var(--oa-impact-orange) !important;
      opacity: 1 !important;
    }
    svg path.oa-deletion-impact {
      fill: none !important;
      stroke-width: 3px !important;
    }

    .oa-deletion-preview-summary {
      display: grid;
      gap: 6px;
      margin: 8px 0 12px;
      padding: 10px 12px;
      border: 1px solid rgba(217, 119, 6, .35);
      border-radius: 8px;
      background: rgba(217, 119, 6, .05);
      font-size: 12px;
      line-height: 1.45;
    }
    .oa-deletion-preview-summary strong {
      color: var(--oa-delete-red);
    }
    .oa-deletion-preview-effect {
      color: var(--oa-impact-orange);
    }
    .oa-deletion-preview-key {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      font-size: 11px;
      font-weight: 650;
    }
    .oa-deletion-preview-key .target { color: var(--oa-delete-red); }
    .oa-deletion-preview-key .impact { color: var(--oa-impact-orange); }

    #modelTextual .oa-deletion-target,
    #modelDetails .oa-deletion-target {
      color: var(--oa-delete-red) !important;
      background: var(--oa-delete-red-bg);
      border-radius: 4px;
      text-decoration: line-through;
      text-decoration-thickness: 1.5px;
    }
    #modelTextual .oa-deletion-impact,
    #modelDetails .oa-deletion-impact {
      color: var(--oa-impact-orange) !important;
      background: var(--oa-impact-orange-bg);
      border-radius: 4px;
    }

    .sysml-code-placeholder .oa-sysml-deletion-line,
    .sysml-code-placeholder .oa-sysml-impact-line,
    .sysml-code-placeholder .oa-sysml-normal-line {
      display: block;
      min-height: 1em;
      white-space: pre;
    }
    .sysml-code-placeholder .oa-sysml-deletion-line {
      color: var(--oa-delete-red);
      background: var(--oa-delete-red-bg);
      text-decoration: line-through;
      text-decoration-thickness: 1.5px;
    }
    .sysml-code-placeholder .oa-sysml-impact-line {
      color: var(--oa-impact-orange);
      background: var(--oa-impact-orange-bg);
    }

    #quickActions button.oa-confirm-delete {
      border-color: var(--oa-delete-red) !important;
      color: var(--oa-delete-red) !important;
    }
  `;
  document.head.appendChild(style);
}

function edgeMatches(reference, edge) {
  if (!reference || !edge) return false;
  if (String(reference.source ?? '') !== String(edge.source ?? '')) return false;
  if (String(reference.target ?? '') !== String(edge.target ?? '')) return false;
  if (clean(reference.type) && clean(reference.type) !== clean(edge.type)) return false;
  if (reference.key !== undefined && reference.key !== null && String(reference.key) !== String(edge.key)) {
    return false;
  }
  if (clean(reference.name) && canonical(reference.name) !== canonical(edge.name)) return false;
  return true;
}

function resolveEdgeIds(model, references) {
  const refs = Array.isArray(references) ? references : [];
  const result = new Set();
  (Array.isArray(model?.edges) ? model.edges : []).forEach((edge, index) => {
    if (!refs.some(reference => edgeMatches(reference, edge))) return;
    result.add(clean(edge.id) || projectedEdgeId(edge, index));
  });
  return result;
}

function clearDeletionClasses(root = document) {
  root.querySelectorAll(`.${TARGET_CLASS}, .${IMPACT_CLASS}`).forEach(element => {
    element.classList.remove(TARGET_CLASS, IMPACT_CLASS);
  });
}

function decorateDiagram(model, preview) {
  const tab = document.getElementById('diagramTab');
  if (!tab) return;
  clearDeletionClasses(tab);

  const targetNodes = new Set(preview?.target_node_ids || []);
  const impactNodes = new Set(preview?.impact_node_ids || []);
  targetNodes.forEach(id => {
    tab.querySelectorAll(`[data-node-id="${CSS.escape(String(id))}"]`).forEach(element =>
      element.classList.add(TARGET_CLASS)
    );
  });
  impactNodes.forEach(id => {
    if (targetNodes.has(id)) return;
    tab.querySelectorAll(`[data-node-id="${CSS.escape(String(id))}"]`).forEach(element =>
      element.classList.add(IMPACT_CLASS)
    );
  });

  const targetEdges = resolveEdgeIds(model, preview?.target_edges);
  const impactEdges = resolveEdgeIds(model, preview?.impact_edges);
  targetEdges.forEach(id => {
    tab.querySelectorAll(`[data-edge-id="${CSS.escape(id)}"]`).forEach(element =>
      element.classList.add(TARGET_CLASS)
    );
    tab.querySelectorAll(`[data-port-id^="${CSS.escape(id)}"]`).forEach(element =>
      element.classList.add(TARGET_CLASS)
    );
  });
  impactEdges.forEach(id => {
    if (targetEdges.has(id)) return;
    tab.querySelectorAll(`[data-edge-id="${CSS.escape(id)}"]`).forEach(element =>
      element.classList.add(IMPACT_CLASS)
    );
    tab.querySelectorAll(`[data-port-id^="${CSS.escape(id)}"]`).forEach(element =>
      element.classList.add(IMPACT_CLASS)
    );
  });

  renderSummary(tab, preview, 'diagram');
}

function textMatch(text, token, mode = 'contains') {
  const value = canonical(text);
  const wanted = canonical(token);
  if (!wanted) return false;
  return mode === 'exact' ? value === wanted : value.includes(wanted);
}

function decorateTextProjection(model, preview) {
  const roots = [document.getElementById('modelTextual'), document.getElementById('modelDetails')].filter(Boolean);
  const target = preview?.target || {};
  const targetTokens = preview?.target_tokens || [];
  const impactTokens = preview?.impact_tokens || [];
  const mode = target.match_mode || (target.kind === 'node' ? 'exact' : 'contains');

  roots.forEach(root => {
    clearDeletionClasses(root);
    const candidates = root.querySelectorAll(
      '.tree-item-name, .tree-line, .detail-name, .detail-row, .detail-value'
    );
    candidates.forEach(element => {
      const text = element.textContent || '';
      const targetHit = targetTokens.some(token => textMatch(text, token, mode));
      if (targetHit) {
        element.classList.add(TARGET_CLASS);
        return;
      }
      const impactHit = impactTokens.some(token => textMatch(text, token, 'contains'));
      if (impactHit || targetTokens.some(token => textMatch(text, token, 'contains'))) {
        element.classList.add(IMPACT_CLASS);
      }
    });
  });

  const textView = document.getElementById('utilityTextView');
  if (textView) renderSummary(textView, preview, 'text');
}

function targetSysmlKeyword(target) {
  if (target?.kind === 'characteristic') return 'attribute';
  if (target?.kind === 'edge') {
    if (target.type === 'OPERATIONAL_EXCHANGE') return 'flow';
    if (target.type === 'COMMUNICATION_MEAN') return 'connection';
    return '';
  }
  return ({
    OperationalCapability: 'requirement',
    OperationalActivity: 'action',
    OperationalActor: 'part',
    OperationalEntity: 'part',
  })[target?.type] || '';
}

function sysmlContainsStem(line, token) {
  const tokenStem = stem(token);
  if (!tokenStem) return false;
  return line.includes(`_${tokenStem}`) || line.includes(` ${tokenStem}`);
}

function isTargetSysmlLine(line, preview) {
  const target = preview?.target || {};
  const keyword = targetSysmlKeyword(target);
  const tokens = preview?.target_tokens || [];
  const trimmed = line.trim();
  if (tokens.some(token => canonical(trimmed) === canonical(`// name: ${token}`))) return true;
  if (!keyword || !trimmed.includes(keyword)) return false;
  return tokens.some(token => sysmlContainsStem(line, token));
}

function isImpactSysmlLine(line, preview) {
  const impactTokens = preview?.impact_tokens || [];
  if (impactTokens.some(token => sysmlContainsStem(line, token))) return true;
  const targetTokens = preview?.target_tokens || [];
  return targetTokens.some(token => sysmlContainsStem(line, token));
}

function decorateSysml(model, preview) {
  const view = document.getElementById('utilitySysmlView');
  const code = view?.querySelector('code');
  if (!code) return;

  const text = String(model?.sysml_v2 || '').trimEnd() || '// No confirmed Operational Analysis elements yet.';
  if (!preview) {
    if (code.dataset.deletionDecorated === 'true') {
      code.textContent = text;
      delete code.dataset.deletionDecorated;
    }
    removeSummary(view, 'sysml');
    return;
  }

  code.innerHTML = '';
  text.split('\n').forEach(line => {
    const span = document.createElement('span');
    span.className = isTargetSysmlLine(line, preview)
      ? 'oa-sysml-deletion-line'
      : isImpactSysmlLine(line, preview)
        ? 'oa-sysml-impact-line'
        : 'oa-sysml-normal-line';
    span.textContent = line || '\u200b';
    code.appendChild(span);
  });
  code.dataset.deletionDecorated = 'true';
  renderSummary(view, preview, 'sysml');
}

function summaryId(kind) {
  return `oaDeletionPreviewSummary-${kind}`;
}

function removeSummary(root, kind) {
  root?.querySelector(`#${CSS.escape(summaryId(kind))}`)?.remove();
}

function renderSummary(root, preview, kind) {
  if (!root) return;
  removeSummary(root, kind);
  if (!preview) return;

  const targetName = clean(preview.target?.name || 'selected item');
  const summary = document.createElement('div');
  summary.id = summaryId(kind);
  summary.className = 'oa-deletion-preview-summary';
  summary.setAttribute('role', 'status');

  const key = document.createElement('div');
  key.className = 'oa-deletion-preview-key';
  key.innerHTML = '<span class="target">Red — pending deletion</span><span class="impact">Orange — affected</span>';
  summary.appendChild(key);

  const target = document.createElement('strong');
  target.textContent = `Pending deletion: ${targetName}`;
  summary.appendChild(target);

  (preview.effects || []).forEach(effect => {
    const line = document.createElement('div');
    line.className = 'oa-deletion-preview-effect';
    line.textContent = `• ${effect}`;
    summary.appendChild(line);
  });

  if (kind === 'diagram') {
    const toolbar = root.querySelector('.oa-diagram-toolbar');
    if (toolbar?.nextSibling) root.insertBefore(summary, toolbar.nextSibling);
    else root.prepend(summary);
  } else if (kind === 'sysml') {
    const container = root.querySelector('.sysml-text-placeholder') || root;
    const pre = container.querySelector('pre');
    if (pre) container.insertBefore(summary, pre);
    else container.appendChild(summary);
  } else {
    const tab = root.querySelector('#textualTab');
    if (tab) root.insertBefore(summary, tab);
    else root.prepend(summary);
  }
}

function decorateConfirmation(preview) {
  document.querySelectorAll('#quickActions button').forEach(button => {
    button.classList.remove('oa-confirm-delete');
    if (preview && canonical(button.textContent) === 'yes') {
      button.classList.add('oa-confirm-delete');
    }
  });
}

function applyDeletionPreview(model = {}) {
  const preview = activePreview(model);
  if (!preview) {
    clearDeletionClasses(document);
    ['diagram', 'text', 'sysml'].forEach(kind => {
      const root = kind === 'diagram'
        ? document.getElementById('diagramTab')
        : kind === 'text'
          ? document.getElementById('utilityTextView')
          : document.getElementById('utilitySysmlView');
      removeSummary(root, kind);
    });
    decorateConfirmation(null);
    decorateSysml(model, null);
    return;
  }

  decorateDiagram(model, preview);
  decorateTextProjection(model, preview);
  decorateSysml(model, preview);
  decorateConfirmation(preview);
}

installStyle();

const priorApplyState = window.applyState;
if (typeof priorApplyState === 'function' && !priorApplyState.__oaDeletionPreviewAware) {
  const wrapped = function deletionPreviewAwareApplyState(state) {
    const result = priorApplyState(state);
    applyDeletionPreview(state?.model || {});
    return result;
  };
  wrapped.__oaDeletionPreviewAware = true;
  window.applyState = wrapped;
}

window.addEventListener('mbse:model-projections-updated', event => {
  applyDeletionPreview(event.detail?.model || {});
});
window.addEventListener('oa:diagram-model-rendered', () => {
  const model = window.mbseModelProjectionSync?.getLatest?.().model || {};
  applyDeletionPreview(model);
});

applyDeletionPreview(window.mbseModelProjectionSync?.getLatest?.().model || {});

export {applyDeletionPreview};
