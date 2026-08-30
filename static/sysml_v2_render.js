(() => {
  if (window.__oaSysmlV2RenderInstalled) return;
  window.__oaSysmlV2RenderInstalled = true;

  let latestSysmlText = '';

  function roots() {
    const view = document.getElementById('utilitySysmlView');
    if (!view) return null;
    const container = view.querySelector('.sysml-text-placeholder') || view;
    const heading = container.querySelector('.sysml-placeholder-heading');
    const note = container.querySelector('p');
    const code = container.querySelector('code');
    return {view, container, heading, note, code};
  }

  function suggestedSysmlFilename() {
    const modelName = String(
      document.getElementById('modelFileName')?.textContent || 'Operational Analysis model'
    )
      .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_')
      .replace(/\s+/g, ' ')
      .trim();
    return `${modelName || 'Operational Analysis model'}.sysml`;
  }

  async function writeSysmlToChosenLocation(text) {
    const filename = suggestedSysmlFilename();

    if (typeof window.showSaveFilePicker === 'function') {
      const handle = await window.showSaveFilePicker({
        suggestedName: filename,
        types: [{
          description: 'SysML v2 model',
          accept: {'text/plain': ['.sysml']}
        }]
      });
      const writable = await handle.createWritable();
      await writable.write(text);
      await writable.close();
      return;
    }

    const blob = new Blob([text], {type: 'text/plain;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  function ensureExportButton(ui) {
    if (!ui?.container || !ui?.code) return null;
    let button = ui.container.querySelector('#exportSysmlButton');
    if (button) return button;

    const actions = document.createElement('div');
    actions.className = 'model-file-actions sysml-export-actions';

    button = document.createElement('button');
    button.id = 'exportSysmlButton';
    button.className = 'ghost-button model-file-button';
    button.type = 'button';
    button.textContent = 'Export .sysml';
    button.title = 'Export the current ArcadiaOA-based SysML v2 projection as a .sysml file';
    button.setAttribute('aria-label', 'Export SysML V2 model as .sysml file');

    button.addEventListener('click', async () => {
      const text = latestSysmlText || String(ui.code.textContent || '');
      if (!text.trim()) return;

      const originalLabel = 'Export .sysml';
      button.disabled = true;
      button.textContent = 'Exporting…';
      try {
        await writeSysmlToChosenLocation(text.endsWith('\n') ? text : `${text}\n`);
        button.textContent = 'Exported';
        window.setTimeout(() => {
          if (button.isConnected) button.textContent = originalLabel;
        }, 1200);
      } catch (error) {
        if (error?.name !== 'AbortError') {
          console.error('SysML v2 export failed.', error);
          button.textContent = 'Export failed';
          window.setTimeout(() => {
            if (button.isConnected) button.textContent = originalLabel;
          }, 1800);
        } else {
          button.textContent = originalLabel;
        }
      } finally {
        button.disabled = false;
      }
    });

    actions.appendChild(button);
    const pre = ui.container.querySelector('pre');
    if (pre) ui.container.insertBefore(actions, pre);
    else ui.container.appendChild(actions);
    return button;
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
    latestSysmlText = text;
    ui.code.textContent = text || '// No confirmed Operational Analysis elements yet.';
    ui.code.setAttribute('aria-label', 'Generated SysML V2 text');
    ensureExportButton(ui);
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
