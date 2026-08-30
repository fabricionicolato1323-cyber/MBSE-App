(() => {
  const workspaceRoot = document.getElementById('workspace');
  if (!workspaceRoot) return;

  const query = new URLSearchParams(window.location.search);
  const rawDetachedPanel = query.get('detachedPanel');
  const legacyUtilityView = query.get('utilityView') === 'sysml' ? 'sysml' : 'text';
  const outputViewNames = ['text', 'sysml', 'diagram', 'details'];
  const outputViewSet = new Set(outputViewNames);
  const detachedViewName = rawDetachedPanel === 'utility'
    ? legacyUtilityView
    : outputViewSet.has(rawDetachedPanel) ? rawDetachedPanel : null;
  const detachedOutputWindow = Boolean(detachedViewName);

  const panels = new Map(
    [...workspaceRoot.querySelectorAll('.workspace-panel[data-panel]')]
      .map(panel => [panel.dataset.panel, panel])
  );

  const panelToggles = new Map(
    [...document.querySelectorAll('[data-panel-toggle]')]
      .map(button => [button.dataset.panelToggle, button])
  );

  const splitters = {
    completion: workspaceRoot.querySelector('[data-splitter="completion"]'),
    output: workspaceRoot.querySelector('[data-splitter="output"]'),
  };

  const outputPanel = panels.get('output');
  const outputTabs = [...document.querySelectorAll('[data-output-tab]')];
  const outputViews = [...document.querySelectorAll('[data-output-view]')];
  const outputPanelTitle = document.getElementById('outputPanelTitle');
  const outputDetachedEmpty = document.getElementById('outputDetachedEmpty');
  const outputPopups = new Map();
  const outputPopupMonitors = new Map();
  let activeOutputView = detachedViewName || 'text';

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function outputViewLabel(name) {
    return ({
      text: 'Pseudo-code',
      sysml: 'SysML V2',
      diagram: 'Diagram',
      details: 'Details',
    })[name] || 'Model output';
  }

  function panelIsDockedUsable(name) {
    const panel = panels.get(name);
    return Boolean(
      panel &&
      !panel.hidden &&
      !panel.classList.contains('is-floating') &&
      !panel.classList.contains('is-minimized') &&
      !panel.classList.contains('is-maximized')
    );
  }

  function refreshSplitters() {
    if (splitters.completion) {
      splitters.completion.hidden = !(
        panelIsDockedUsable('completion') &&
        (panelIsDockedUsable('chat') || panelIsDockedUsable('output'))
      );
    }
    if (splitters.output) {
      splitters.output.hidden = !(
        panelIsDockedUsable('output') &&
        (panelIsDockedUsable('chat') || panelIsDockedUsable('completion'))
      );
    }
  }

  function refreshPanelToggle(name) {
    const panel = panels.get(name);
    const button = panelToggles.get(name);
    if (!panel || !button) return;
    const visible = !panel.hidden;
    button.classList.toggle('active', visible);
    button.setAttribute('aria-pressed', visible ? 'true' : 'false');
  }

  function popupForView(name) {
    const popup = outputPopups.get(name);
    if (popup && !popup.closed) return popup;
    if (popup) {
      outputPopups.delete(name);
      stopOutputPopupMonitor(name);
    }
    return null;
  }

  function viewIsDetached(name) {
    return Boolean(popupForView(name));
  }

  function firstDockedOutputView() {
    return outputViewNames.find(name => !viewIsDetached(name)) || null;
  }

  function setActiveOutputView(name, {allowDetached = false} = {}) {
    if (!outputViewSet.has(name)) return false;
    if (!detachedOutputWindow && viewIsDetached(name) && !allowDetached) {
      popupForView(name)?.focus();
      return false;
    }

    activeOutputView = name;
    outputTabs.forEach(button => {
      const selected = button.dataset.outputTab === name;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-selected', selected ? 'true' : 'false');
    });
    outputViews.forEach(view => {
      const selected = view.dataset.outputView === name;
      view.classList.toggle('active', selected);
      view.hidden = !selected;
    });
    if (outputDetachedEmpty) outputDetachedEmpty.hidden = true;
    if (outputPanelTitle) {
      outputPanelTitle.textContent = detachedOutputWindow ? outputViewLabel(name) : 'Model output';
    }
    refreshOutputTabs();
    if (outputPanel) refreshPanelControls(outputPanel);
    return true;
  }

  function showAllViewsDetachedState() {
    activeOutputView = null;
    outputViews.forEach(view => {
      view.classList.remove('active');
      view.hidden = true;
    });
    outputTabs.forEach(button => {
      button.classList.remove('active');
      button.setAttribute('aria-selected', 'false');
    });
    if (outputDetachedEmpty) outputDetachedEmpty.hidden = false;
    if (outputPanelTitle) outputPanelTitle.textContent = 'Model output';
    if (outputPanel) refreshPanelControls(outputPanel);
  }

  function refreshOutputTabs() {
    outputTabs.forEach(button => {
      const name = button.dataset.outputTab;
      const detached = !detachedOutputWindow && viewIsDetached(name);
      button.classList.toggle('is-detached-view', detached);
      button.dataset.detached = detached ? 'true' : 'false';
      button.title = detached
        ? `${outputViewLabel(name)} is open in a separate browser window. Click to focus it.`
        : `Show ${outputViewLabel(name)}`;
    });
  }

  outputTabs.forEach(button => {
    button.addEventListener('click', () => {
      const name = button.dataset.outputTab;
      if (!outputViewSet.has(name)) return;
      if (!detachedOutputWindow && viewIsDetached(name)) {
        popupForView(name)?.focus();
        return;
      }
      setActiveOutputView(name, {allowDetached: detachedOutputWindow});
    });
  });

  function refreshPanelControls(panel) {
    const name = panel.dataset.panel;
    const floating = panel.classList.contains('is-floating');
    const minimized = panel.classList.contains('is-minimized');
    const maximized = panel.classList.contains('is-maximized');
    const dockButton = panel.querySelector('[data-panel-action="dock"]');
    const minimizeButton = panel.querySelector('[data-panel-action="minimize"]');
    const maximizeButton = panel.querySelector('[data-panel-action="maximize"]');

    if (dockButton) {
      if (name === 'output') {
        if (detachedOutputWindow) {
          dockButton.disabled = false;
          dockButton.textContent = '↙';
          dockButton.title = `Dock ${outputViewLabel(detachedViewName)} in the main browser window`;
        } else if (activeOutputView) {
          dockButton.disabled = false;
          dockButton.textContent = '↗';
          dockButton.title = `Open ${outputViewLabel(activeOutputView)} in a new browser window`;
        } else {
          dockButton.disabled = true;
          dockButton.textContent = '↗';
          dockButton.title = 'All output views are already undocked';
        }
      } else {
        dockButton.disabled = false;
        dockButton.textContent = floating ? '↙' : '↗';
        dockButton.title = floating ? 'Dock panel' : 'Undock panel';
      }
      dockButton.setAttribute('aria-label', dockButton.title);
    }

    if (minimizeButton) {
      minimizeButton.textContent = minimized ? '▣' : '−';
      minimizeButton.title = minimized ? 'Restore panel' : 'Minimize panel';
      minimizeButton.setAttribute('aria-label', minimizeButton.title);
    }

    if (maximizeButton) {
      const detachedFullscreen = detachedOutputWindow && name === 'output' && document.fullscreenElement;
      maximizeButton.textContent = maximized || detachedFullscreen ? '❐' : '□';
      maximizeButton.title = maximized || detachedFullscreen
        ? 'Restore panel size'
        : name === 'output' ? 'Full screen panel' : 'Maximize panel';
      maximizeButton.setAttribute('aria-label', maximizeButton.title);
    }
  }

  function clearFloatingGeometry(panel) {
    panel.style.left = '';
    panel.style.top = '';
    panel.style.width = '';
    panel.style.height = '';
  }

  function undockPanel(panel) {
    if (panel.classList.contains('is-floating')) return;
    const rect = panel.getBoundingClientRect();
    panel.classList.remove('is-minimized', 'is-maximized');
    panel.classList.add('is-floating');
    panel.style.left = `${clamp(rect.left, 8, Math.max(8, window.innerWidth - 300))}px`;
    panel.style.top = `${clamp(rect.top, 8, Math.max(8, window.innerHeight - 180))}px`;
    panel.style.width = `${clamp(rect.width, 320, Math.max(320, window.innerWidth - 16))}px`;
    panel.style.height = `${clamp(rect.height, 240, Math.max(240, window.innerHeight - 16))}px`;
    refreshPanelControls(panel);
    refreshSplitters();
  }

  function dockPanel(panel) {
    if (!panel.classList.contains('is-floating')) return;
    panel.classList.remove('is-floating', 'is-minimized', 'is-maximized');
    clearFloatingGeometry(panel);
    refreshPanelControls(panel);
    refreshSplitters();
  }

  function stopOutputPopupMonitor(name) {
    const monitor = outputPopupMonitors.get(name);
    if (monitor) window.clearInterval(monitor);
    outputPopupMonitors.delete(name);
  }

  function markOutputViewReturned(name, {activate = false, showPanel = false} = {}) {
    if (detachedOutputWindow || !outputViewSet.has(name)) return;
    stopOutputPopupMonitor(name);
    outputPopups.delete(name);
    refreshOutputTabs();

    if (showPanel && outputPanel) {
      outputPanel.hidden = false;
      outputPanel.classList.remove('is-minimized');
      refreshPanelToggle('output');
    }

    if (activate || !activeOutputView) {
      setActiveOutputView(name);
    } else if (outputDetachedEmpty && !outputDetachedEmpty.hidden) {
      setActiveOutputView(name);
    }
    refreshSplitters();
  }

  function redockOutputView(name, {closePopup = false, showPanel = true} = {}) {
    if (detachedOutputWindow || !outputViewSet.has(name)) return;
    const popup = popupForView(name);
    if (closePopup && popup && !popup.closed) popup.close();
    markOutputViewReturned(name, {activate: true, showPanel});
  }

  function openOutputBrowserWindow(name) {
    if (detachedOutputWindow || !outputViewSet.has(name)) return;
    const existing = popupForView(name);
    if (existing) {
      existing.focus();
      return;
    }

    const url = new URL(window.location.href);
    url.searchParams.delete('utilityView');
    url.searchParams.set('detachedPanel', name);
    const popup = window.open(
      url.toString(),
      `mbse-${name}-output`,
      'popup=yes,width=820,height=900,resizable=yes,scrollbars=yes'
    );

    if (!popup) {
      const status = document.getElementById('statusLine');
      if (status) status.textContent = 'The browser blocked the new output window. Allow pop-ups for this local app and try again.';
      return;
    }

    outputPopups.set(name, popup);
    stopOutputPopupMonitor(name);
    outputPopupMonitors.set(name, window.setInterval(() => {
      const current = outputPopups.get(name);
      if (!current || current.closed) markOutputViewReturned(name);
    }, 500));

    refreshOutputTabs();
    const nextView = firstDockedOutputView();
    if (nextView) setActiveOutputView(nextView);
    else showAllViewsDetachedState();
  }

  function toggleMinimize(panel) {
    if (panel.classList.contains('is-maximized')) panel.classList.remove('is-maximized');
    panel.classList.toggle('is-minimized');
    refreshPanelControls(panel);
    refreshSplitters();
  }

  async function toggleDetachedFullscreen(panel) {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch (_error) {
      panel.classList.toggle('is-maximized');
    }
    refreshPanelControls(panel);
  }

  function toggleMaximize(panel) {
    if (detachedOutputWindow && panel.dataset.panel === 'output') {
      void toggleDetachedFullscreen(panel);
      return;
    }
    if (panel.classList.contains('is-minimized')) panel.classList.remove('is-minimized');
    panel.classList.toggle('is-maximized');
    refreshPanelControls(panel);
    refreshSplitters();
  }

  function setPanelVisible(name, visible) {
    const panel = panels.get(name);
    if (!panel) return;
    panel.hidden = !visible;
    if (visible) {
      panel.classList.remove('is-minimized');
      refreshPanelControls(panel);
    }
    refreshPanelToggle(name);
    refreshSplitters();
  }

  function requestRedockFromDetachedWindow() {
    if (!detachedOutputWindow || !detachedViewName) return;
    if (window.opener && !window.opener.closed) {
      window.opener.postMessage(
        {type: 'mbse-redock-output-view', view: detachedViewName},
        window.location.origin
      );
    }
    window.close();
  }

  panels.forEach((panel, name) => {
    refreshPanelControls(panel);
    refreshPanelToggle(name);

    panel.querySelectorAll('[data-panel-action]').forEach(button => {
      button.addEventListener('click', event => {
        event.stopPropagation();
        const action = button.dataset.panelAction;
        if (action === 'dock') {
          if (name === 'output') {
            if (detachedOutputWindow) requestRedockFromDetachedWindow();
            else if (activeOutputView) openOutputBrowserWindow(activeOutputView);
          } else if (panel.classList.contains('is-floating')) {
            dockPanel(panel);
          } else {
            undockPanel(panel);
          }
        } else if (action === 'minimize') {
          toggleMinimize(panel);
        } else if (action === 'maximize') {
          toggleMaximize(panel);
        } else if (action === 'close') {
          if (detachedOutputWindow && name === 'output') requestRedockFromDetachedWindow();
          else setPanelVisible(name, false);
        }
      });
    });

    const dragHandle = panel.querySelector('.panel-drag-handle');
    if (dragHandle) {
      dragHandle.addEventListener('pointerdown', event => {
        if (!panel.classList.contains('is-floating')) return;
        if (panel.classList.contains('is-maximized')) return;
        if (event.target.closest('button, select, textarea, input')) return;

        const rect = panel.getBoundingClientRect();
        const startX = event.clientX;
        const startY = event.clientY;
        const startLeft = rect.left;
        const startTop = rect.top;
        dragHandle.setPointerCapture?.(event.pointerId);

        const onMove = moveEvent => {
          const maxLeft = Math.max(8, window.innerWidth - Math.min(rect.width, 280) - 8);
          const maxTop = Math.max(8, window.innerHeight - 52);
          panel.style.left = `${clamp(startLeft + moveEvent.clientX - startX, 8, maxLeft)}px`;
          panel.style.top = `${clamp(startTop + moveEvent.clientY - startY, 8, maxTop)}px`;
        };

        const onUp = () => {
          window.removeEventListener('pointermove', onMove);
          window.removeEventListener('pointerup', onUp);
        };

        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', onUp, {once: true});
      });
    }
  });

  panelToggles.forEach((button, name) => {
    button.addEventListener('click', () => {
      const panel = panels.get(name);
      if (!panel) return;
      setPanelVisible(name, panel.hidden);
    });
  });

  function installSplitter(splitter, cssVariable, panelName, minWidth, maxWidth, direction = 'right') {
    if (!splitter) return;
    splitter.addEventListener('pointerdown', event => {
      if (!panelIsDockedUsable(panelName)) return;
      const panel = panels.get(panelName);
      const rect = panel.getBoundingClientRect();
      const startX = event.clientX;
      const startWidth = rect.width;
      splitter.classList.add('is-dragging');
      splitter.setPointerCapture?.(event.pointerId);

      const onMove = moveEvent => {
        const delta = moveEvent.clientX - startX;
        const next = direction === 'left' ? startWidth + delta : startWidth - delta;
        document.documentElement.style.setProperty(
          cssVariable,
          `${clamp(next, minWidth, Math.min(maxWidth, window.innerWidth * .62))}px`
        );
      };

      const onUp = () => {
        splitter.classList.remove('is-dragging');
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onUp);
      };

      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp, {once: true});
    });
  }

  installSplitter(splitters.completion, '--completion-width', 'completion', 190, 520, 'left');
  installSplitter(splitters.output, '--output-width', 'output', 300, 820, 'right');

  function countCharacteristics(nodes) {
    return nodes.reduce(
      (total, node) => total + (Array.isArray(node.characteristics) ? node.characteristics.length : 0),
      0
    );
  }

  function oaCompletionItems(model) {
    const nodes = Array.isArray(model?.nodes) ? model.nodes : [];
    const edges = Array.isArray(model?.edges) ? model.edges : [];
    const goals = nodes.filter(node => node.type === 'OperationalCapability');
    const participants = nodes.filter(node =>
      ['OperationalActor', 'OperationalEntity'].includes(node.type)
    );
    const actions = nodes.filter(node => node.type === 'OperationalActivity');
    const participantIds = new Set(participants.map(node => node.id));
    const actionIds = new Set(actions.map(node => node.id));
    const performs = edges.filter(edge =>
      edge.type === 'PERFORMS' &&
      participantIds.has(edge.source) &&
      actionIds.has(edge.target)
    );
    const ownedActions = new Set(performs.map(edge => edge.target));
    const activeOwners = new Set(performs.map(edge => edge.source));
    const exchanges = edges.filter(edge => edge.type === 'OPERATIONAL_EXCHANGE');
    const communication = edges.filter(edge => edge.type === 'COMMUNICATION_MEAN');
    const characteristicCount = countCharacteristics(nodes);

    let ownershipRatio = 0;
    if (actions.length && participants.length) {
      ownershipRatio = Math.min(
        1,
        ((ownedActions.size / actions.length) + (activeOwners.size / participants.length)) / 2
      );
    }

    return [
      {
        label: 'Operational goal',
        weight: 15,
        ratio: goals.length ? 1 : 0,
        detail: goals.length ? `${goals.length} defined` : 'Add at least one operational goal.'
      },
      {
        label: 'Participants / context',
        weight: 15,
        ratio: participants.length ? 1 : 0,
        detail: participants.length ? `${participants.length} defined` : 'Add the people, organizations, systems or context involved.'
      },
      {
        label: 'Operational activities',
        weight: 20,
        ratio: actions.length ? 1 : 0,
        detail: actions.length ? `${actions.length} defined` : 'Add the actions that must occur operationally.'
      },
      {
        label: 'Activity ownership',
        weight: 15,
        ratio: ownershipRatio,
        detail: !actions.length || !participants.length
          ? 'Activities and participants are needed before ownership can be checked.'
          : `${ownedActions.size}/${actions.length} activities assigned · ${activeOwners.size}/${participants.length} participants with activities`
      },
      {
        label: 'Operational interactions',
        weight: 15,
        ratio: exchanges.length ? 1 : 0,
        detail: exchanges.length ? `${exchanges.length} interaction(s) defined` : 'Add exchanges between operational activities when information or material flows.'
      },
      {
        label: 'Communication means',
        weight: 10,
        ratio: communication.length ? 1 : 0,
        detail: communication.length ? `${communication.length} communication link(s) defined` : 'Add how relevant participants communicate.'
      },
      {
        label: 'Characteristics / limits',
        weight: 10,
        ratio: characteristicCount ? 1 : 0,
        detail: characteristicCount ? `${characteristicCount} characteristic(s) captured` : 'Add quantitative limits, ranges or other relevant characteristics.'
      }
    ];
  }

  function renderOACompletion(model) {
    const percentRoot = document.getElementById('completionPercent');
    const barRoot = document.getElementById('completionBarFill');
    const listRoot = document.getElementById('completionList');
    if (!percentRoot || !barRoot || !listRoot) return;

    const items = oaCompletionItems(model || {});
    const percent = Math.round(
      items.reduce((sum, item) => sum + item.weight * item.ratio, 0)
    );

    percentRoot.textContent = `${percent}%`;
    barRoot.style.width = `${percent}%`;
    barRoot.parentElement?.setAttribute('aria-label', `${percent}% structurally complete`);

    listRoot.innerHTML = '';
    items.forEach(item => {
      const state = item.ratio >= .999 ? 'done' : item.ratio > 0 ? 'partial' : 'missing';
      const row = document.createElement('div');
      row.className = `completion-item ${state}`;

      const icon = document.createElement('span');
      icon.className = 'completion-item-icon';
      icon.textContent = state === 'done' ? '✓' : state === 'partial' ? '◐' : '·';

      const copy = document.createElement('div');
      copy.className = 'completion-item-copy';
      const title = document.createElement('strong');
      title.textContent = item.label;
      const detail = document.createElement('span');
      detail.textContent = item.detail;
      copy.append(title, detail);
      row.append(icon, copy);
      listRoot.appendChild(row);
    });
  }

  if (typeof applyState === 'function') {
    const baseApplyState = applyState;
    applyState = function oaWorkspaceApplyState(state) {
      baseApplyState(state);
      renderOACompletion(state?.model || {});
    };
  }

  if (typeof clearRenderedSession === 'function') {
    const baseClearRenderedSession = clearRenderedSession;
    clearRenderedSession = function oaWorkspaceClearRenderedSession() {
      baseClearRenderedSession();
      renderOACompletion({nodes: [], edges: []});
    };
  }

  document.querySelectorAll('.viewpoint-tab.placeholder').forEach(button => {
    button.addEventListener('click', event => event.preventDefault());
  });

  if (detachedOutputWindow && detachedViewName) {
    document.body.classList.add('detached-output-window');
    panels.forEach((panel, name) => {
      panel.hidden = name !== 'output';
    });
    if (outputPanel) {
      outputPanel.hidden = false;
      outputPanel.classList.remove('is-floating', 'is-minimized', 'is-maximized');
    }
    setActiveOutputView(detachedViewName, {allowDetached: true});
    window.addEventListener('beforeunload', () => {
      if (window.opener && !window.opener.closed) {
        window.opener.postMessage(
          {type: 'mbse-output-window-closed', view: detachedViewName},
          window.location.origin
        );
      }
    });
  } else {
    setActiveOutputView('text');
    window.addEventListener('message', event => {
      if (event.origin !== window.location.origin) return;
      if (!event.data || typeof event.data !== 'object') return;
      const name = event.data.view;
      if (!outputViewSet.has(name)) return;
      if (event.data.type === 'mbse-redock-output-view') {
        redockOutputView(name, {closePopup: true, showPanel: true});
      } else if (event.data.type === 'mbse-output-window-closed') {
        markOutputViewReturned(name);
      }
    });
  }

  document.addEventListener('fullscreenchange', () => {
    panels.forEach(panel => refreshPanelControls(panel));
  });

  window.addEventListener('resize', refreshSplitters);
  renderOACompletion({nodes: [], edges: []});
  panels.forEach((_panel, name) => refreshPanelToggle(name));
  refreshOutputTabs();
  refreshSplitters();
})();