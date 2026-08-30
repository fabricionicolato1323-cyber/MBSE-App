(() => {
  if (window.__mbseChangeImpactPresentationInstalled) return;
  window.__mbseChangeImpactPresentationInstalled = true;

  let latestModel = {};

  function entries(presentation, key) {
    return Array.isArray(presentation?.[key])
      ? presentation[key].filter(item => item && typeof item === 'object')
      : [];
  }

  function namesFor(items) {
    return items
      .map(item => String(item.name || '').trim())
      .filter(Boolean)
      .sort((a, b) => b.length - a.length);
  }

  function textMatches(text, names) {
    const value = String(text || '').toLocaleLowerCase();
    return names.some(name => value.includes(name.toLocaleLowerCase()));
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

  function applyDiagramHighlights(modified, impacted) {
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
  }

  function addDeleteSummary(presentation) {
    if (presentation?.operation !== 'delete') return;
    const modified = entries(presentation, 'modified');
    if (!modified.length) return;
    const name = String(modified[0].name || modified[0].id || 'model element');

    const textual = document.getElementById('modelTextual');
    if (textual) {
      const note = document.createElement('div');
      note.className = 'mbse-change-summary modified';
      note.textContent = `Deleted: ${name}`;
      textual.prepend(note);
    }

    const sysmlContainer = document.querySelector('#utilitySysmlView .sysml-text-placeholder');
    if (sysmlContainer) {
      const note = document.createElement('div');
      note.className = 'mbse-change-summary modified';
      note.textContent = `Deleted from the current model: ${name}`;
      const pre = sysmlContainer.querySelector('pre');
      if (pre) sysmlContainer.insertBefore(note, pre);
      else sysmlContainer.appendChild(note);
    }
  }

  function apply(model = latestModel) {
    latestModel = model || {};
    const presentation = latestModel?.presentation || {};
    const modified = entries(presentation, 'modified');
    const impacted = entries(presentation, 'impacted');

    clearDomHighlights();
    if (!modified.length && !impacted.length) return;

    const modifiedNames = namesFor(modified);
    const impactedNames = namesFor(impacted);
    applyTextualHighlights(modifiedNames, impactedNames);
    applySysmlHighlights(modifiedNames, impactedNames);
    applyDiagramHighlights(modified, impacted);
    addDeleteSummary(presentation);
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
