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

  function level1Projection(model = {}) {
    const explicit = model?.sysml_v2_level1;
    if (explicit && typeof explicit === 'object') return explicit;

    const nodes = Array.isArray(model?.nodes) ? model.nodes : [];
    const edges = Array.isArray(model?.edges) ? model.edges : [];
    const scenarios = Array.isArray(model?.scenarios) ? model.scenarios : [];
    const drafts = Array.isArray(model?.drafts) ? model.drafts : [];
    return {
      level: 1,
      phase: 'A',
      kind: 'model',
      label: 'Level 1 · Model',
      scope: 'complete_model',
      status: nodes.length || edges.length || scenarios.length ? 'ready' : 'empty',
      text: String(model?.sysml_v2 || ''),
      counts: {
        elements: nodes.length,
        relationships: edges.length,
        scenarios: scenarios.filter(item => item?.valid !== false).length,
        temporary_items: drafts.length,
      },
      sam_write_performed: false,
    };
  }

  function suggestedSysmlFilename() {
    const modelName = String(
      document.getElementById('modelFileName')?.textContent || 'Operational Analysis model'
    )
      .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_')
      .replace(/\s+/g, ' ')
      .trim();
    return `${modelName || 'Operational Analysis model'}.level1.sysml`;
  }

  async function writeSysmlToChosenLocation(text) {
    const filename = suggestedSysmlFilename();

    if (typeof window.showSaveFilePicker === 'function') {
      const handle = await window.showSaveFilePicker({
        suggestedName: filename,
        types: [{
          description: 'SysML v2 Level 1 model',
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

  function ensureLevelControls(ui) {
    if (!ui?.container || !ui?.code) return null;
    let root = ui.container.querySelector('#sysmlLevelControls');
    if (root) {
      return {
        root,
        summary: root.querySelector('#sysmlLevel1Summary'),
      };
    }

    root = document.createElement('div');
    root.id = 'sysmlLevelControls';
    root.className = 'model-file-actions sysml-level-actions';
    root.setAttribute('aria-label', 'SysML V2 output level');

    const level1 = document.createElement('button');
    level1.id = 'sysmlLevel1Button';
    level1.className = 'ghost-button model-file-button active';
    level1.type = 'button';
    level1.textContent = 'Level 1 · Model';
    level1.setAttribute('aria-pressed', 'true');
    level1.title = 'Complete semantic model projection';

    const level2 = document.createElement('button');
    level2.id = 'sysmlLevel2Button';
    level2.className = 'ghost-button model-file-button';
    level2.type = 'button';
    level2.textContent = 'Level 2 · Views';
    level2.disabled = true;
    level2.title = 'Level 2 view definitions will be implemented after Level 1 transfer is validated.';

    const summary = document.createElement('span');
    summary.id = 'sysmlLevel1Summary';
    summary.className = 'model-file-location-note';
    summary.setAttribute('aria-live', 'polite');

    root.append(level1, level2, summary);
    const pre = ui.container.querySelector('pre');
    if (pre) ui.container.insertBefore(root, pre);
    else ui.container.appendChild(root);
    return {root, summary};
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
    button.textContent = 'Export Level 1 .sysml';
    button.title = 'Export the complete Level 1 SysML v2 model projection as a .sysml file';
    button.setAttribute('aria-label', 'Export Level 1 SysML V2 model as .sysml file');

    button.addEventListener('click', async () => {
      const text = latestSysmlText || String(ui.code.textContent || '');
      if (!text.trim()) return;

      const originalLabel = 'Export Level 1 .sysml';
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
          console.error('SysML v2 Level 1 export failed.', error);
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

    const level1 = level1Projection(model);
    const counts = level1?.counts || {};

    if (ui.heading) ui.heading.textContent = 'SysML V2 · Level 1 — Model';
    if (ui.note) {
      ui.note.textContent =
        'Generated live from the complete confirmed Operational Analysis model. Level 1A is preview/export only; no model data is written to SAM.';
    }

    const controls = ensureLevelControls(ui);
    if (controls?.summary) {
      const statusText = level1?.status === 'ready' ? 'Preview ready' : 'Waiting for confirmed model content';
      controls.summary.textContent =
        `${statusText} · ${Number(counts.elements || 0)} elements · ${Number(counts.relationships || 0)} relationships · ${Number(counts.scenarios || 0)} scenarios · SAM not written`;
    }

    const text = String(level1?.text || model?.sysml_v2 || '').trimEnd();
    latestSysmlText = text;
    ui.code.textContent = text || '// No confirmed Operational Analysis elements yet.';
    ui.code.setAttribute('aria-label', 'Generated SysML V2 text — Level 1 model');
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