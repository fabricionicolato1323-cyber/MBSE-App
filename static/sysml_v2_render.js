(() => {
  if (window.__oaSysmlV2RenderInstalled) return;
  window.__oaSysmlV2RenderInstalled = true;

  let latestSysmlText = '';
  let latestLevel1 = null;
  let latestSamSync = null;

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
      snapshot_digest: '',
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

  function ensureActionArea(ui) {
    let actions = ui.container.querySelector('#sysmlLevel1Actions');
    if (actions) return actions;
    actions = document.createElement('div');
    actions.id = 'sysmlLevel1Actions';
    actions.className = 'model-file-actions sysml-export-actions';
    const pre = ui.container.querySelector('pre');
    if (pre) ui.container.insertBefore(actions, pre);
    else ui.container.appendChild(actions);
    return actions;
  }

  function ensureExportButton(ui) {
    if (!ui?.container || !ui?.code) return null;
    let button = ui.container.querySelector('#exportSysmlButton');
    if (button) return button;

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

    ensureActionArea(ui).appendChild(button);
    return button;
  }

  function currentSyncMatches(level1) {
    return Boolean(
      latestSamSync?.snapshot_digest &&
      level1?.snapshot_digest &&
      latestSamSync.snapshot_digest === level1.snapshot_digest
    );
  }

  function deltaText(delta = {}) {
    return `CREATE ${Number(delta.create || 0)} · UPDATE ${Number(delta.update || 0)} · DELETE ${Number(delta.delete || 0)} · UNCHANGED ${Number(delta.unchanged || 0)}`;
  }

  function relationshipChangeDetails(plan = {}) {
    const rows = [];
    const append = (label, items) => {
      for (const item of Array.isArray(items) ? items : []) {
        const edge = item?.edge || item?.old_edge || {};
        const name = String(edge?.name || item?.new_name || item?.old_name || edge?.type || 'Relationship');
        const type = String(edge?.type || item?.type || 'RELATIONSHIP');
        const source = String(edge?.source || '?');
        const target = String(edge?.target || '?');
        rows.push(`${label} ${type} · ${name} · ${source} → ${target}`);
      }
    };
    append('CREATE', plan.relationship_creates);
    append('UPDATE', plan.relationship_updates);
    append('DELETE', plan.relationship_deletes);
    return rows.length ? `\n${rows.join('\n')}` : '';
  }

  function updateLevel1Summary(ui, level1) {
    const controls = ensureLevelControls(ui);
    if (!controls?.summary) return;
    const counts = level1?.counts || {};
    const statusText = level1?.status === 'ready'
      ? 'Preview ready'
      : 'Waiting for confirmed model content';
    let samText = 'SAM not synchronized';
    if (currentSyncMatches(level1)) {
      const container = latestSamSync?.target?.root_package_name;
      const location = container ? ` · under ${container}` : '';
      const timing = Number(
        latestSamSync?.timings?.total_with_verification_seconds ??
        latestSamSync?.timings?.total_seconds ?? 0
      );
      const timingText = timing > 0 ? ` · ${timing.toFixed(1)} s` : '';
      const delta = latestSamSync?.delta;
      const deltaSummary = delta && Number(delta.create || 0) + Number(delta.update || 0) + Number(delta.delete || 0) > 0
        ? ` · Δ ${Number(delta.create || 0)}/${Number(delta.update || 0)}/${Number(delta.delete || 0)}`
        : '';
      samText = `SAM synchronized · ${latestSamSync.package_name}${location}${deltaSummary}${timingText}`;
    }
    controls.summary.textContent =
      `${statusText} · ${Number(counts.elements || 0)} elements · ${Number(counts.relationships || 0)} relationships · ${Number(counts.scenarios || 0)} scenarios · ${samText}`;
  }

  async function readJson(response) {
    return response.json().catch(() => ({}));
  }

  function blockedChangeMessage(plan) {
    const pending = Array.isArray(plan?.unsupported_changes)
      ? plan.unsupported_changes.filter(Boolean)
      : [];
    if (pending.length) {
      return `This local change set cannot be synchronized yet:\n\n- ${pending.join('\n- ')}\n\nNo SAM data has been changed.`;
    }
    const unsupported =
      Number(plan?.unsupported_nodes?.length || 0) +
      Number(plan?.unsupported_relations?.length || 0);
    return unsupported
      ? `SAM synchronization is blocked by ${unsupported} unsupported model item(s). No SAM data has been changed.`
      : 'SAM synchronization is blocked for the current model. No SAM data has been changed.';
  }

  function buildReviewMessage(plan) {
    const target = plan.target || {};
    const projectLabel = target.project_name
      ? `${target.project_name} (${target.project_id || plan.target_project_id})`
      : (target.project_id || plan.target_project_id);
    const rootLabel = target.root_package_name || '(project root)';
    const library = plan.library || {};
    const instance = plan.instance || {};
    const delta = plan.delta || {};
    const relationshipDelta = plan.relationship_delta || {};
    const scenarioDelta = plan.scenario_delta || {};

    if (plan.sync_status === 'never_synchronized') {
      const relationCreate = Number(relationshipDelta.create || 0);
      const scenarioCreate = Number(scenarioDelta.create || 0);
      return (
        `Create the initial managed Level 1 baseline in SAM?\n\n` +
        `Project: ${projectLabel}\n` +
        `Target container: ${rootLabel}\n` +
        `Library: ${library.package_name || 'MBSE_ArcadiaOA_Library_v1'} (create if missing, otherwise reuse)\n` +
        `Instance: ${instance.package_name || plan.package_name}\n\n` +
        `Initial Change Set\n` +
        `${deltaText(delta)}\n` +
        `RELATIONSHIPS CREATE ${relationCreate}\n` +
        `SCENARIOS CREATE ${scenarioCreate}\n\n` +
        `SAM preflight: connected successfully. No write has occurred yet.\n` +
        `Synchronize now?`
      );
    }

    return (
      `Synchronize these local Level 1 changes with SAM?\n\n` +
      `Project: ${projectLabel}\n` +
      `Target container: ${rootLabel}\n` +
      `Library: ${library.package_name || 'MBSE_ArcadiaOA_Library_v1'} (reused, no write)\n` +
      `Instance: ${instance.package_name || plan.package_name} (reused)\n\n` +
      `Change Set\n` +
      `ELEMENTS\n${deltaText(delta)}\n` +
      `RELATIONSHIPS\n${deltaText(relationshipDelta)}${relationshipChangeDetails(plan)}\n` +
      `SCENARIOS: unchanged\n\n` +
      `SAM preflight: connected successfully. No write has occurred yet.\n` +
      `Only this reviewed delta will be synchronized. Continue?`
    );
  }

  function ensureSamSendButton(ui) {
    if (!ui?.container || !ui?.code) return null;
    let button = ui.container.querySelector('#sendLevel1ToSamButton');
    if (button) return button;

    button = document.createElement('button');
    button.id = 'sendLevel1ToSamButton';
    button.className = 'ghost-button model-file-button';
    button.type = 'button';
    button.textContent = 'Review / Sync with SAM';
    button.title = 'Connect read-only, review the local Level 1 change set, then synchronize only after explicit confirmation';
    button.setAttribute('aria-label', 'Review and synchronize Level 1 changes with SAM');

    button.addEventListener('click', async () => {
      if (!latestLevel1 || latestLevel1.status !== 'ready') return;
      const normalLabel = 'Review / Sync with SAM';
      button.disabled = true;
      button.textContent = 'Checking SAM target…';
      try {
        const planResponse = await fetch('/api/sam/level1/plan', {cache: 'no-store'});
        const planData = await readJson(planResponse);
        if (!planResponse.ok || !planData.plan) {
          throw new Error(planData.error || 'The SAM change set could not be prepared.');
        }
        const plan = planData.plan;
        if (
          latestLevel1.snapshot_digest &&
          plan.snapshot_digest !== latestLevel1.snapshot_digest
        ) {
          throw new Error('The model changed while the SAM change set was being prepared. Review the current Level 1 output and try again.');
        }

        if (plan.sync_status === 'up_to_date') {
          latestSamSync = {
            status: 'already_synced',
            mode: 'incremental_noop',
            snapshot_digest: plan.snapshot_digest,
            package_name: plan.instance?.package_name || plan.package_name,
            sam_package_id: plan.instance?.package_id,
            target: plan.target,
            delta: plan.delta || {create: 0, update: 0, delete: 0, unchanged: Number(plan.counts?.elements || 0)},
            relationship_delta: plan.relationship_delta || {create: 0, update: 0, delete: 0, unchanged: Number(plan.counts?.relationships || 0)},
            timings: {total_seconds: 0},
          };
          button.textContent = 'Level 1 in SAM';
          updateLevel1Summary(ui, latestLevel1);
          return;
        }

        if (plan.status !== 'ready' || plan.supported === false) {
          throw new Error(blockedChangeMessage(plan));
        }

        const approved = window.confirm(buildReviewMessage(plan));
        if (!approved) {
          button.textContent = normalLabel;
          return;
        }

        button.textContent = 'Synchronizing delta…';
        const sendResponse = await fetch('/api/sam/level1/send', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            confirm: true,
            snapshot_digest: plan.snapshot_digest,
          }),
        });
        const sendData = await readJson(sendResponse);
        if (!sendResponse.ok || !sendData.result) {
          throw new Error(sendData.error || 'The reviewed Level 1 change set could not be synchronized with SAM.');
        }
        if (sendData.result.verified_in_sam !== true) {
          throw new Error('SAM returned from synchronization, but fresh verification did not confirm the reviewed Level 1 state.');
        }
        latestSamSync = sendData.result;
        button.textContent = latestSamSync.status === 'already_synced'
          ? 'Level 1 in SAM'
          : 'Synchronized';
        updateLevel1Summary(ui, latestLevel1);
        window.setTimeout(() => {
          if (!button.isConnected) return;
          button.textContent = currentSyncMatches(latestLevel1)
            ? 'Level 1 in SAM'
            : normalLabel;
        }, 1400);
      } catch (error) {
        console.error('Level 1B SAM synchronization failed.', error);
        const message = error?.message || 'SAM synchronization failed.';
        button.textContent = 'SAM sync blocked / failed';
        const controls = ensureLevelControls(ui);
        if (controls?.summary) {
          controls.summary.textContent = `SAM sync blocked / failed · ${message}`;
        }
        window.setTimeout(() => {
          window.alert(`SAM Level 1 synchronization\n\n${message}`);
        }, 0);
      } finally {
        button.disabled = latestLevel1?.status !== 'ready';
      }
    });

    ensureActionArea(ui).appendChild(button);
    return button;
  }

  function renderSysmlV2(model = {}) {
    const ui = roots();
    if (!ui?.code) return;

    const level1 = level1Projection(model);
    latestLevel1 = level1;

    if (ui.heading) ui.heading.textContent = 'SysML V2 · Level 1 — Model';
    if (ui.note) {
      ui.note.textContent =
        'Generated live from the complete confirmed Operational Analysis model. Work remains local; SAM writes occur only after a read-only preflight, change-set review, and explicit confirmation.';
    }

    updateLevel1Summary(ui, level1);

    const text = String(level1?.text || model?.sysml_v2 || '').trimEnd();
    latestSysmlText = text;
    ui.code.textContent = text || '// No confirmed Operational Analysis elements yet.';
    ui.code.setAttribute('aria-label', 'Generated SysML V2 text — Level 1 model');
    ensureExportButton(ui);
    const samButton = ensureSamSendButton(ui);
    if (samButton) {
      samButton.disabled = level1?.status !== 'ready';
      if (currentSyncMatches(level1)) samButton.textContent = 'Level 1 in SAM';
      else if (!samButton.textContent.includes('…') && samButton.textContent !== 'SAM sync blocked / failed') {
        samButton.textContent = 'Review / Sync with SAM';
      }
    }
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
      latestSamSync = null;
      renderSysmlV2({});
    };
  }

  window.addEventListener('mbse:model-projections-updated', event => {
    renderSysmlV2(event.detail?.model || {});
  });

  const latest = window.mbseModelProjectionSync?.getLatest?.().model;
  renderSysmlV2(latest || {});
})();