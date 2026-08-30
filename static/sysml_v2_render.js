(() => {
  if (window.__oaSysmlV2RenderInstalled) return;
  window.__oaSysmlV2RenderInstalled = true;

  function roots() {
    const view = document.getElementById('utilitySysmlView');
    if (!view) return null;
    const container = view.querySelector('.sysml-text-placeholder') || view;
    const heading = container.querySelector('.sysml-placeholder-heading');
    const note = container.querySelector('p');
    const code = container.querySelector('code');
    return {view, container, heading, note, code};
  }

  function renderSysmlV2(model = {}) {
    const ui = roots();
    if (!ui?.code) return;

    if (ui.heading) ui.heading.textContent = 'SysML V2 textual output';
    if (ui.note) {
      ui.note.textContent =
        'Generated live from the confirmed Operational Analysis model using a conservative SysML v2 subset intended for Ansys SAM textual import.';
    }

    const text = String(model?.sysml_v2 || '').trimEnd();
    ui.code.textContent = text || '// No confirmed Operational Analysis elements yet.';
    ui.code.setAttribute('aria-label', 'Generated SysML V2 text');
  }

  const baseApplyState = window.applyState;
  if (typeof baseApplyState === 'function') {
    window.applyState = function sysmlV2AwareApplyState(state) {
      baseApplyState(state);
      renderSysmlV2(state?.model || {});
    };
  }

  const baseClearRenderedSession = window.clearRenderedSession;
  if (typeof baseClearRenderedSession === 'function') {
    window.clearRenderedSession = function sysmlV2AwareClearRenderedSession() {
      baseClearRenderedSession();
      renderSysmlV2({});
    };
  }

  window.addEventListener('mbse:model-projections-updated', event => {
    renderSysmlV2(event.detail?.model || {});
  });

  const latest = window.mbseModelProjectionSync?.getLatest?.().model;
  renderSysmlV2(latest || {});
})();
