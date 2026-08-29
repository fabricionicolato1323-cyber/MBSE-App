(() => {
  'use strict';

  const PARTICIPANTS = new Set(['OperationalEntity', 'OperationalActor']);
  const LAYOUT_VERSION = 3;
  const MIN = {
    OperationalEntity: [270, 160],
    OperationalActor: [230, 145],
    OperationalActivity: [180, 64],
    OperationalCapability: [200, 70],
    Pending: [180, 64],
  };
  const PAD = 22;
  const HEADER = 50;
  const GAP = 14;
  const PARTICIPANT_GAP = 24;
  const SECTION_GAP = 20;
  const MAX_NESTED_ROW_WIDTH = 900;
  const SVG_NS = 'http://www.w3.org/2000/svg';

  const state = {
    session: 'default',
    model: {nodes: [], drafts: [], edges: []},
    modelSignature: '',
    byId: new Map(),
    parent: new Map(),
    parentRelation: new Map(),
    children: new Map(),
    layout: new Map(),
    invalidContainments: [],
    selected: new Set(),
    mode: 'normal',
    showCapabilities: true,
    view: {x: 28, y: 28, zoom: 1},
    drag: null,
    edgeRenderFrame: 0,
    suppressClickUntil: 0,
    ready: false,
  };

  const el = {};

  const clean = value => String(value ?? '').replace(/\s+/g, ' ').trim();
  const minFor = type => MIN[type] || [180, 64];
  const typeName = type => ({
    OperationalEntity: 'Operational Entity',
    OperationalActor: 'Operational Actor',
    OperationalActivity: 'Operational Activity',
    OperationalCapability: 'Operational Capability',
    Pending: 'Temporary input',
  })[type] || clean(type) || 'Model element';
  const selectionKey = (kind, id) => `${kind}:${id}`;
  const storageKey = () => `oa-diagram-layout:${state.session}`;

  function isCapability(node) {
    return node?.type === 'OperationalCapability';
  }

  function isVisibleNode(node) {
    return Boolean(node) && (state.showCapabilities || !isCapability(node));
  }

  function isVisibleId(id) {
    return isVisibleNode(state.byId.get(id));
  }

  function modelSignature(model) {
    const nodes = [...(model.nodes || []), ...(model.drafts || [])]
      .map(node => [node.id, node.type, node.name, node.status])
      .sort((a, b) => String(a[0]).localeCompare(String(b[0])));
    const edges = (model.edges || [])
      .map(edge => [
        edge.id || edge.key || '',
        edge.source,
        edge.target,
        edge.type,
        edge.name || '',
        Array.isArray(edge.exchange_refs) ? edge.exchange_refs : [],
      ])
      .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
    return JSON.stringify({nodes, edges});
  }

  function validContainment(parent, child) {
    if (!parent || !child) return false;
    if (parent.type === 'OperationalEntity') return PARTICIPANTS.has(child.type);
    if (parent.type === 'OperationalActor') return child.type === 'OperationalActor';
    return false;
  }

  function validVisualLocation(parent, child) {
    return parent?.type === 'OperationalEntity' && PARTICIPANTS.has(child?.type);
  }

  function wouldCreateVisualCycle(childId, parentId) {
    let current = parentId;
    const seen = new Set();
    while (current && !seen.has(current)) {
      if (current === childId) return true;
      seen.add(current);
      current = state.parent.get(current);
    }
    return false;
  }

  function installMarkup() {
    const tab = document.getElementById('diagramTab');
    if (!tab || document.getElementById('oaDiagramViewport')) return;
    tab.querySelector('.diagram-placeholder')?.remove();

    const toolbar = document.createElement('div');
    toolbar.className = 'oa-diagram-toolbar';
    toolbar.innerHTML = `
      <div class="oa-diagram-tools">
        <button id="oaDiagramZoomOut" class="oa-diagram-tool" type="button" aria-label="Zoom out">−</button>
        <button id="oaDiagramZoomIn" class="oa-diagram-tool" type="button" aria-label="Zoom in">+</button>
        <button id="oaDiagramFit" class="oa-diagram-tool" type="button">Fit</button>
        <button id="oaDiagramReset" class="oa-diagram-tool" type="button">Reset layout</button>
        <button id="oaDiagramCapabilitiesToggle" class="oa-diagram-tool oa-diagram-toggle active" type="button" aria-pressed="true">Capabilities: On</button>
      </div>
      <span id="oaDiagramMode" class="oa-diagram-mode-label">Normal selection</span>`;

    const viewport = document.createElement('div');
    viewport.id = 'oaDiagramViewport';
    viewport.className = 'oa-diagram-viewport';
    viewport.tabIndex = 0;
    viewport.setAttribute('aria-label', 'Interactive Operational Analysis diagram');
    viewport.innerHTML = `
      <div id="oaDiagramScene" class="oa-diagram-scene">
        <div id="oaDiagramContainers" class="oa-diagram-containers"></div>
        <svg id="oaDiagramEdges" class="oa-diagram-edges" aria-label="Model connections"></svg>
        <div id="oaDiagramNodes" class="oa-diagram-nodes"></div>
        <div id="oaDiagramPorts" class="oa-diagram-ports"></div>
      </div>
      <div id="oaDiagramEmpty" class="oa-diagram-empty">The diagram will appear here as the model is built.</div>`;

    const status = document.createElement('div');
    status.id = 'oaDiagramStatus';
    status.className = 'oa-diagram-selection-status';
    status.setAttribute('aria-live', 'polite');
    status.textContent = 'Click an element to select it. Ctrl/Cmd-click keeps multiple elements selected.';

    const legacy = tab.querySelector('.legacy-diagram-layer');
    tab.insertBefore(toolbar, legacy);
    tab.insertBefore(viewport, legacy);
    tab.insertBefore(status, legacy);
  }

  function updateCapabilitiesButton() {
    const button = document.getElementById('oaDiagramCapabilitiesToggle');
    if (!button) return;
    button.textContent = `Capabilities: ${state.showCapabilities ? 'On' : 'Off'}`;
    button.setAttribute('aria-pressed', state.showCapabilities ? 'true' : 'false');
    button.classList.toggle('active', state.showCapabilities);
  }

  function init() {
    if (state.ready) return true;
    installMarkup();
    Object.assign(el, {
      tab: document.getElementById('diagramTab'),
      viewport: document.getElementById('oaDiagramViewport'),
      scene: document.getElementById('oaDiagramScene'),
      containers: document.getElementById('oaDiagramContainers'),
      edges: document.getElementById('oaDiagramEdges'),
      nodes: document.getElementById('oaDiagramNodes'),
      ports: document.getElementById('oaDiagramPorts'),
      empty: document.getElementById('oaDiagramEmpty'),
      status: document.getElementById('oaDiagramStatus'),
      mode: document.getElementById('oaDiagramMode'),
    });
    if (!el.tab || !el.viewport || !el.scene || !el.containers || !el.edges || !el.nodes || !el.ports) return false;

    state.ready = true;
    el.viewport.addEventListener('pointerdown', beginPan);
    el.viewport.addEventListener('pointermove', onPointerMove);
    el.viewport.addEventListener('pointerup', endPointer);
    el.viewport.addEventListener('pointercancel', endPointer);
    el.viewport.addEventListener('wheel', event => {
      event.preventDefault();
      zoom(event.deltaY < 0 ? 1.12 : 0.89, event.clientX, event.clientY);
    }, {passive: false});

    document.getElementById('oaDiagramZoomIn')?.addEventListener('click', () => zoom(1.2));
    document.getElementById('oaDiagramZoomOut')?.addEventListener('click', () => zoom(0.82));
    document.getElementById('oaDiagramFit')?.addEventListener('click', fitView);
    document.getElementById('oaDiagramReset')?.addEventListener('click', resetLayout);
    document.getElementById('oaDiagramCapabilitiesToggle')?.addEventListener('click', () => {
      state.showCapabilities = !state.showCapabilities;
      updateCapabilitiesButton();
      render();
      persist();
      requestAnimationFrame(() => fitView(false));
    });
    document.querySelector('[data-tab="diagram"]')?.addEventListener('click', () => requestAnimationFrame(() => {
      renderEdges();
      if (!loadSaved().view) fitView(false);
    }));
    updateCapabilitiesButton();
    return true;
  }

  function buildModel(model) {
    const nodes = [...(model.nodes || []), ...(model.drafts || [])];
    const edges = model.edges || [];
    state.byId = new Map(nodes.map(node => [node.id, node]));
    state.parent = new Map();
    state.parentRelation = new Map();
    state.children = new Map();
    state.invalidContainments = [];

    const addParent = (child, parent, relation) => {
      if (!child || !parent || child === parent || state.parent.has(child)) return false;
      if (wouldCreateVisualCycle(child, parent)) return false;
      state.parent.set(child, parent);
      state.parentRelation.set(child, relation);
      if (!state.children.has(parent)) state.children.set(parent, []);
      state.children.get(parent).push(child);
      return true;
    };

    // Structural composition has visual precedence over location.
    edges.filter(edge => edge.type === 'CONTAINS').forEach(edge => {
      const parent = state.byId.get(edge.source);
      const child = state.byId.get(edge.target);
      if (!PARTICIPANTS.has(parent?.type) || !PARTICIPANTS.has(child?.type)) return;
      if (!validContainment(parent, child)) {
        state.invalidContainments.push(edge);
        return;
      }
      addParent(child.id, parent.id, 'CONTAINS');
    });

    // A LOCATED_IN relationship may be used as a visual enclosure without
    // changing its semantic meaning to CONTAINS. This mirrors the textual view.
    edges.filter(edge => edge.type === 'LOCATED_IN').forEach(edge => {
      const child = state.byId.get(edge.source);
      const parent = state.byId.get(edge.target);
      if (state.parent.has(child?.id) || !validVisualLocation(parent, child)) return;
      addParent(child.id, parent.id, 'LOCATED_IN');
    });

    // Activities are visually enclosed by their confirmed performer.
    edges.filter(edge => edge.type === 'PERFORMS').forEach(edge => {
      const parent = state.byId.get(edge.source);
      const child = state.byId.get(edge.target);
      if (PARTICIPANTS.has(parent?.type) && child?.type === 'OperationalActivity') {
        addParent(child.id, parent.id, 'PERFORMS');
      }
    });
  }

  function childNodes(id, predicate = () => true) {
    return (state.children.get(id) || [])
      .map(child => state.byId.get(child))
      .filter(node => node && predicate(node));
  }

  function packRows(items) {
    const rows = [];
    let row = {items: [], width: 0, height: 0};
    for (const item of items) {
      const gap = row.items.length ? PARTICIPANT_GAP : 0;
      if (row.items.length && row.width + gap + item.size.w > MAX_NESTED_ROW_WIDTH) {
        rows.push(row);
        row = {items: [], width: 0, height: 0};
      }
      const nextGap = row.items.length ? PARTICIPANT_GAP : 0;
      row.items.push(item);
      row.width += nextGap + item.size.w;
      row.height = Math.max(row.height, item.size.h);
    }
    if (row.items.length) rows.push(row);
    return rows;
  }

  function measureParticipant(id, seen = new Set()) {
    const node = state.byId.get(id);
    const [minW, minH] = minFor(node?.type);
    if (!node || seen.has(id)) return {w: minW, h: minH};

    const next = new Set(seen);
    next.add(id);
    const activities = childNodes(id, child => child.type === 'OperationalActivity');
    const activitySizes = activities.map(activity => ({id: activity.id, size: {w: minFor(activity.type)[0], h: minFor(activity.type)[1]}}));
    const activityWidth = activitySizes.length ? Math.max(...activitySizes.map(item => item.size.w)) : 0;
    const activityHeight = activitySizes.reduce((sum, item, index) => sum + item.size.h + (index ? GAP : 0), 0);

    const participantItems = childNodes(id, child => PARTICIPANTS.has(child.type))
      .map(child => ({id: child.id, size: measureParticipant(child.id, next)}));
    const rows = packRows(participantItems);
    const participantWidth = rows.length ? Math.max(...rows.map(row => row.width)) : 0;
    const participantHeight = rows.reduce((sum, row, index) => sum + row.height + (index ? PARTICIPANT_GAP : 0), 0);
    const sectionGap = activityHeight && participantHeight ? SECTION_GAP : 0;

    return {
      w: Math.max(minW, activityWidth + PAD * 2, participantWidth + PAD * 2),
      h: Math.max(minH, HEADER + PAD + activityHeight + sectionGap + participantHeight + PAD),
    };
  }

  function put(id, x, y, w, h) {
    const [minW, minH] = minFor(state.byId.get(id)?.type);
    state.layout.set(id, {x, y, w: Math.max(minW, w), h: Math.max(minH, h)});
  }

  function placeParticipant(id, x, y, seen = new Set()) {
    if (seen.has(id)) return;

    // Measure before adding this participant to the cycle guard. The previous
    // implementation measured with `next`, causing every container to collapse
    // to its minimum size and leaving children outside the parent rectangle.
    const size = measureParticipant(id, seen);
    const next = new Set(seen);
    next.add(id);
    put(id, x, y, size.w, size.h);

    let cursorY = y + HEADER + PAD;
    const activities = childNodes(id, child => child.type === 'OperationalActivity');
    for (const activity of activities) {
      const [, h] = minFor(activity.type);
      const availableWidth = Math.max(minFor(activity.type)[0], size.w - PAD * 2);
      put(activity.id, x + PAD, cursorY, availableWidth, h);
      cursorY += h + GAP;
    }
    if (activities.length) cursorY -= GAP;

    const participantItems = childNodes(id, child => PARTICIPANTS.has(child.type))
      .map(child => ({id: child.id, size: measureParticipant(child.id, next)}));
    const rows = packRows(participantItems);
    if (activities.length && rows.length) cursorY += SECTION_GAP;

    rows.forEach((row, rowIndex) => {
      let cursorX = x + PAD;
      row.items.forEach(item => {
        placeParticipant(item.id, cursorX, cursorY, next);
        cursorX += item.size.w + PARTICIPANT_GAP;
      });
      cursorY += row.height + (rowIndex < rows.length - 1 ? PARTICIPANT_GAP : 0);
    });
  }

  function autoLayout() {
    state.layout = new Map();
    const roots = [...state.byId.values()].filter(node => !state.parent.has(node.id));
    let x = 60;
    let y = 60;
    let rowH = 0;
    for (const node of roots) {
      let w;
      let h;
      if (PARTICIPANTS.has(node.type)) {
        const size = measureParticipant(node.id);
        w = size.w;
        h = size.h;
        placeParticipant(node.id, x, y);
      } else {
        [w, h] = minFor(node.type);
        put(node.id, x, y, w, h);
      }
      if (x + w > 1350) {
        x = 60;
        y += rowH + 70;
        rowH = 0;
      } else {
        x += w + 70;
        rowH = Math.max(rowH, h);
      }
    }
    applySaved();
    normalizeContainmentGeometry();
  }

  function loadSaved() {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey()) || '{}') || {};
      return saved.version === LAYOUT_VERSION ? saved : {};
    } catch (_error) {
      return {};
    }
  }

  function applySaved() {
    const saved = loadSaved();
    for (const [id, value] of Object.entries(saved.nodes || {})) {
      if (!state.layout.has(id)) continue;
      const [minW, minH] = minFor(state.byId.get(id)?.type);
      const current = state.layout.get(id);
      state.layout.set(id, {
        x: Number.isFinite(value.x) ? value.x : current.x,
        y: Number.isFinite(value.y) ? value.y : current.y,
        w: Math.max(minW, Number(value.w) || current.w),
        h: Math.max(minH, Number(value.h) || current.h),
      });
    }
    if (saved.view && Number.isFinite(saved.view.zoom)) state.view = saved.view;
  }

  function persist() {
    const nodes = {};
    state.layout.forEach((value, id) => {
      nodes[id] = {x: value.x, y: value.y, w: value.w, h: value.h};
    });
    try {
      localStorage.setItem(storageKey(), JSON.stringify({
        version: LAYOUT_VERSION,
        nodes,
        view: state.view,
        showCapabilities: state.showCapabilities,
      }));
    } catch (_error) {
      // Layout persistence is optional.
    }
  }

  function descendants(id, result = []) {
    for (const child of state.children.get(id) || []) {
      result.push(child);
      descendants(child, result);
    }
    return result;
  }

  function depth(id) {
    let d = 0;
    let parent = state.parent.get(id);
    const seen = new Set();
    while (parent && !seen.has(parent)) {
      seen.add(parent);
      d += 1;
      parent = state.parent.get(parent);
    }
    return d;
  }

  function moveSubtree(id, dx, dy) {
    for (const childId of [id, ...descendants(id)]) {
      const position = state.layout.get(childId);
      if (!position) continue;
      position.x += dx;
      position.y += dy;
      updateNode(childId);
    }
  }

  function requiredContainerSize(id) {
    const position = state.layout.get(id);
    const node = state.byId.get(id);
    const [baseW, baseH] = minFor(node?.type);
    if (!position || !PARTICIPANTS.has(node?.type)) return {w: baseW, h: baseH};
    let w = baseW;
    let h = baseH;
    for (const childId of state.children.get(id) || []) {
      const child = state.layout.get(childId);
      if (!child) continue;
      w = Math.max(w, child.x + child.w + PAD - position.x);
      h = Math.max(h, child.y + child.h + PAD - position.y);
    }
    return {w, h};
  }

  function constrainOrExpandParent(id) {
    const ownerId = state.parent.get(id);
    const position = state.layout.get(id);
    const owner = state.layout.get(ownerId);
    if (!ownerId || !position || !owner) return;

    const minX = owner.x + PAD;
    const minY = owner.y + HEADER + PAD;
    let correctionX = 0;
    let correctionY = 0;
    if (position.x < minX) correctionX = minX - position.x;
    if (position.y < minY) correctionY = minY - position.y;
    if (correctionX || correctionY) moveSubtree(id, correctionX, correctionY);

    const corrected = state.layout.get(id);
    owner.w = Math.max(owner.w, corrected.x + corrected.w + PAD - owner.x);
    owner.h = Math.max(owner.h, corrected.y + corrected.h + PAD - owner.y);
    updateNode(ownerId);
    constrainOrExpandParent(ownerId);
  }

  function normalizeContainmentGeometry() {
    const childIds = [...state.parent.keys()].sort((a, b) => depth(b) - depth(a));
    childIds.forEach(constrainOrExpandParent);
    [...state.byId.keys()]
      .sort((a, b) => depth(b) - depth(a))
      .forEach(id => {
        const node = state.byId.get(id);
        const position = state.layout.get(id);
        if (!position || !PARTICIPANTS.has(node?.type)) return;
        const required = requiredContainerSize(id);
        position.w = Math.max(position.w, required.w);
        position.h = Math.max(position.h, required.h);
      });
  }

  function center(id) {
    const position = state.layout.get(id);
    return position ? {x: position.x + position.w / 2, y: position.y + position.h / 2} : null;
  }

  function visibleLayout() {
    return [...state.layout.entries()].filter(([id]) => isVisibleId(id));
  }

  function updateBounds() {
    let maxX = 1200;
    let maxY = 800;
    visibleLayout().forEach(([, position]) => {
      maxX = Math.max(maxX, position.x + position.w + 120);
      maxY = Math.max(maxY, position.y + position.h + 120);
    });
    el.scene.style.width = `${maxX}px`;
    el.scene.style.height = `${maxY}px`;
    el.edges.setAttribute('width', String(maxX));
    el.edges.setAttribute('height', String(maxY));
    el.edges.setAttribute('viewBox', `0 0 ${maxX} ${maxY}`);
  }

  function applyView() {
    el.scene.style.transform = `translate(${state.view.x}px, ${state.view.y}px) scale(${state.view.zoom})`;
  }

  function select(kind, id, event) {
    if (Date.now() < state.suppressClickUntil) return;
    const key = selectionKey(kind, id);
    const additive = state.mode === 'scenario' || event?.ctrlKey || event?.metaKey;
    if (!additive) state.selected.clear();
    if (additive && state.selected.has(key)) state.selected.delete(key);
    else state.selected.add(key);
    updateSelection();
  }

  function selectionPayload() {
    return [...state.selected].map(key => {
      const split = key.indexOf(':');
      return {kind: key.slice(0, split), id: key.slice(split + 1)};
    });
  }

  function updateSelection() {
    document.querySelectorAll('[data-oa-select-key]').forEach(node => {
      const selected = state.selected.has(node.dataset.oaSelectKey);
      node.classList.toggle('selected', selected);
      node.setAttribute('aria-pressed', selected ? 'true' : 'false');
    });
    const selected = selectionPayload();
    if (el.status) {
      if (selected.length) el.status.textContent = `${selected.length} diagram element${selected.length === 1 ? '' : 's'} selected.`;
      else if (state.invalidContainments.length) el.status.textContent = 'Invalid containment kept outside actor: Operational Actors cannot contain Operational Entities.';
      else el.status.textContent = state.mode === 'scenario'
        ? 'Scenario selection mode: click elements to add or remove them.'
        : 'Click an element to select it. Ctrl/Cmd-click keeps multiple elements selected.';
    }
    window.dispatchEvent(new CustomEvent('oa:diagram-selection-change', {detail: {mode: state.mode, selected}}));
  }

  function nodeElement(node) {
    const position = state.layout.get(node.id);
    const div = document.createElement('div');
    div.className = `oa-diagram-node type-${clean(node.type).toLowerCase()} ${node.status === 'temporary' ? 'temporary' : 'confirmed'} ${PARTICIPANTS.has(node.type) ? 'participant-container' : 'leaf-node'}`;
    div.dataset.nodeId = node.id;
    div.dataset.nodeType = node.type;
    div.dataset.oaSelectKey = selectionKey('node', node.id);
    div.tabIndex = 0;
    div.setAttribute('role', 'button');
    div.setAttribute('aria-pressed', 'false');
    Object.assign(div.style, {
      left: `${position.x}px`,
      top: `${position.y}px`,
      width: `${position.w}px`,
      height: `${position.h}px`,
    });

    const header = document.createElement('div');
    header.className = 'oa-diagram-node-header';
    header.innerHTML = `<span class="oa-diagram-node-type">${typeName(node.type)}</span><strong class="oa-diagram-node-title">${clean(node.name || node.id)}</strong>`;
    div.appendChild(header);

    if (PARTICIPANTS.has(node.type)) {
      header.classList.add('oa-diagram-drag-handle');
      header.addEventListener('pointerdown', event => beginMove(event, node.id));
      const hint = document.createElement('small');
      hint.className = 'oa-diagram-containment-hint';
      hint.textContent = node.type === 'OperationalActor' ? 'actors + activities' : 'entities + actors + activities';
      div.appendChild(hint);
    } else {
      div.addEventListener('pointerdown', event => beginMove(event, node.id));
    }

    const resize = document.createElement('button');
    resize.type = 'button';
    resize.className = 'oa-diagram-resize-handle';
    resize.textContent = '↘';
    resize.setAttribute('aria-label', `Resize ${clean(node.name || node.id)}`);
    resize.addEventListener('pointerdown', event => beginResize(event, node.id));
    div.appendChild(resize);

    div.addEventListener('click', event => {
      if (!event.target.closest('.oa-diagram-resize-handle')) select('node', node.id, event);
    });
    div.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        select('node', node.id, event);
      }
    });
    return div;
  }

  function renderNodes() {
    el.containers.innerHTML = '';
    el.nodes.innerHTML = '';
    const nodes = [...state.byId.values()]
      .filter(isVisibleNode)
      .sort((a, b) => depth(a.id) - depth(b.id));
    nodes.forEach(node => {
      const target = PARTICIPANTS.has(node.type) ? el.containers : el.nodes;
      target.appendChild(nodeElement(node));
    });
  }

  function svg(name, attrs = {}) {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  }

  function curve(a, b) {
    const bend = Math.max(34, Math.abs(b.x - a.x) * 0.34);
    const dir = b.x >= a.x ? 1 : -1;
    return `M ${a.x} ${a.y} C ${a.x + bend * dir} ${a.y}, ${b.x - bend * dir} ${b.y}, ${b.x} ${b.y}`;
  }

  function anchorToPoint(id, point) {
    const position = state.layout.get(id);
    const c = center(id);
    if (!position || !c || !point) return null;
    const dx = point.x - c.x;
    const dy = point.y - c.y;
    if (Math.abs(dx) >= Math.abs(dy)) {
      return {x: dx >= 0 ? position.x + position.w : position.x, y: c.y};
    }
    return {x: c.x, y: dy >= 0 ? position.y + position.h : position.y};
  }

  function anchor(id, toward) {
    return anchorToPoint(id, center(toward));
  }

  function edgeId(edge, index) {
    return clean(edge.id) || clean(edge.key) || `${edge.type}:${edge.source}:${edge.target}:${clean(edge.name)}:${index}`;
  }

  function addEdgeInteraction(node, id, type) {
    node.dataset.oaSelectKey = selectionKey('edge', id);
    node.dataset.edgeId = id;
    if (type) node.dataset.edgeType = type;
    node.setAttribute('role', 'button');
    node.setAttribute('tabindex', '0');
    node.setAttribute('aria-pressed', 'false');
    node.addEventListener('click', event => {
      event.stopPropagation();
      select('edge', id, event);
    });
    node.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        select('edge', id, event);
      }
    });
  }

  function drawPath(a, b, className, id, type, {arrow = false} = {}) {
    if (!a || !b) return null;
    const attrs = {d: curve(a, b), class: `oa-diagram-edge ${className}`};
    if (arrow) attrs['marker-end'] = 'url(#oaArrow)';
    const path = svg('path', attrs);
    addEdgeInteraction(path, id, type);
    el.edges.appendChild(path);
    return path;
  }

  function drawLabel(a, b, text, className, id, type, offset = -8) {
    if (!a || !b || !clean(text)) return null;
    const label = svg('text', {
      x: (a.x + b.x) / 2,
      y: (a.y + b.y) / 2 + offset,
      class: `oa-diagram-edge-label ${className || ''}`.trim(),
    });
    label.textContent = clean(text);
    addEdgeInteraction(label, id, type);
    el.edges.appendChild(label);
    return label;
  }

  function addPort(id, participantId, x, y) {
    const port = document.createElement('button');
    port.type = 'button';
    port.className = 'oa-diagram-port';
    port.textContent = 'P';
    port.dataset.oaSelectKey = selectionKey('port', id);
    port.dataset.participantId = participantId;
    port.setAttribute('aria-pressed', 'false');
    Object.assign(port.style, {left: `${x - 10}px`, top: `${y - 10}px`});
    port.setAttribute('aria-label', `Communication port on ${clean(state.byId.get(participantId)?.name || participantId)}`);
    port.addEventListener('click', event => {
      event.stopPropagation();
      select('port', id, event);
    });
    el.ports.appendChild(port);
  }

  function communicationGeometry(edge) {
    if (!PARTICIPANTS.has(state.byId.get(edge.source)?.type) || !PARTICIPANTS.has(state.byId.get(edge.target)?.type)) return null;
    const sourcePoint = anchor(edge.source, edge.target);
    const targetPoint = anchor(edge.target, edge.source);
    if (!sourcePoint || !targetPoint) return null;
    return {sourcePoint, targetPoint};
  }

  function ensureCommunicationRendered(edge, id, geometries) {
    if (geometries.has(id)) return geometries.get(id);
    const geometry = communicationGeometry(edge);
    if (!geometry) return null;
    drawPath(geometry.sourcePoint, geometry.targetPoint, 'communication-mean', id, 'COMMUNICATION_MEAN');
    addPort(`${id}:source`, edge.source, geometry.sourcePoint.x, geometry.sourcePoint.y);
    addPort(`${id}:target`, edge.target, geometry.targetPoint.x, geometry.targetPoint.y);
    drawLabel(geometry.sourcePoint, geometry.targetPoint, clean(edge.name) || 'Communication mean', 'communication-label', id, 'COMMUNICATION_MEAN', -10);
    geometries.set(id, geometry);
    return geometry;
  }

  function performersForActivity(activityId) {
    return (state.model.edges || [])
      .filter(edge => edge.type === 'PERFORMS' && edge.target === activityId && PARTICIPANTS.has(state.byId.get(edge.source)?.type))
      .map(edge => edge.source);
  }

  function communicationConnects(edge, first, second) {
    return (edge.source === first && edge.target === second) || (edge.source === second && edge.target === first);
  }

  function refMatchesExchange(ref, exchange) {
    if (!ref || typeof ref !== 'object') return false;
    if (ref.source_activity_id !== exchange.source || ref.target_activity_id !== exchange.target) return false;
    const name = clean(ref.exchange_name);
    return !name || name === clean(exchange.name);
  }

  function resolveCommunication(exchange, communications) {
    const sourceParticipants = performersForActivity(exchange.source);
    const targetParticipants = performersForActivity(exchange.target);
    if (!sourceParticipants.length || !targetParticipants.length) return null;

    const candidates = [];
    for (const sourceParticipant of sourceParticipants) {
      for (const targetParticipant of targetParticipants) {
        if (sourceParticipant === targetParticipant) continue;
        for (const item of communications) {
          if (!communicationConnects(item.edge, sourceParticipant, targetParticipant)) continue;
          candidates.push({...item, sourceParticipant, targetParticipant});
        }
      }
    }

    const explicit = candidates.filter(candidate =>
      Array.isArray(candidate.edge.exchange_refs) &&
      candidate.edge.exchange_refs.some(ref => refMatchesExchange(ref, exchange))
    );
    if (explicit.length === 1) return explicit[0];
    if (explicit.length > 1) return null;

    // Backward compatibility: old saved models have no exchange_refs. Infer a
    // route only when exactly one communication mean connects the performers.
    const legacy = candidates.filter(candidate =>
      !Array.isArray(candidate.edge.exchange_refs) || candidate.edge.exchange_refs.length === 0
    );
    return legacy.length === 1 ? legacy[0] : null;
  }

  function portPointForParticipant(communication, geometry, participantId) {
    if (communication.source === participantId) return geometry.sourcePoint;
    if (communication.target === participantId) return geometry.targetPoint;
    return null;
  }

  function renderRoutedExchange(exchange, id, match, geometry) {
    const sourcePort = portPointForParticipant(match.edge, geometry, match.sourceParticipant);
    const targetPort = portPointForParticipant(match.edge, geometry, match.targetParticipant);
    const sourceAnchor = anchorToPoint(exchange.source, sourcePort);
    const targetAnchor = anchorToPoint(exchange.target, targetPort);
    if (!sourcePort || !targetPort || !sourceAnchor || !targetAnchor) return;

    drawPath(sourceAnchor, sourcePort, 'operational-exchange routed-segment source-segment', id, 'OPERATIONAL_EXCHANGE', {arrow: true});
    drawLabel(sourceAnchor, sourcePort, clean(exchange.name) || 'Interaction', 'exchange-label', id, 'OPERATIONAL_EXCHANGE', -7);
    drawPath(targetPort, targetAnchor, 'operational-exchange routed-segment target-segment', id, 'OPERATIONAL_EXCHANGE', {arrow: true});
  }

  function renderDirectExchange(edge, id) {
    const a = anchor(edge.source, edge.target);
    const b = anchor(edge.target, edge.source);
    if (!a || !b) return;
    drawPath(a, b, 'operational-exchange direct-exchange', id, 'OPERATIONAL_EXCHANGE', {arrow: true});
    drawLabel(a, b, clean(edge.name) || 'Interaction', 'exchange-label', id, 'OPERATIONAL_EXCHANGE', -7);
  }

  function renderOrdinary(edge, id) {
    if (['CONTAINS', 'PERFORMS', 'LOCATED_IN', 'COMMUNICATION_MEAN', 'OPERATIONAL_EXCHANGE'].includes(edge.type)) return;
    if (!state.showCapabilities && edge.type === 'SUPPORTS_CAPABILITY') return;
    if (!isVisibleId(edge.source) || !isVisibleId(edge.target)) return;
    const a = anchor(edge.source, edge.target);
    const b = anchor(edge.target, edge.source);
    if (!a || !b) return;
    drawPath(a, b, 'ordinary-relation', id, edge.type, {arrow: true});
    drawLabel(a, b, clean(edge.name) || clean(edge.type).toLowerCase().replaceAll('_', ' '), '', id, edge.type, -7);
  }

  function renderEdges() {
    if (!state.ready) return;
    el.edges.innerHTML = '<defs><marker id="oaArrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="oa-diagram-arrow-head"></path></marker></defs>';
    el.ports.innerHTML = '';

    const indexed = (state.model.edges || []).map((edge, index) => ({edge, id: edgeId(edge, index)}));
    const communications = indexed.filter(item => item.edge.type === 'COMMUNICATION_MEAN');
    const exchanges = indexed.filter(item => item.edge.type === 'OPERATIONAL_EXCHANGE');
    const communicationGeometries = new Map();
    const usedCommunications = new Set();

    exchanges.forEach(item => {
      if (!isVisibleId(item.edge.source) || !isVisibleId(item.edge.target)) return;
      const match = resolveCommunication(item.edge, communications);
      if (!match) {
        renderDirectExchange(item.edge, item.id);
        return;
      }
      const geometry = ensureCommunicationRendered(match.edge, match.id, communicationGeometries);
      if (!geometry) {
        renderDirectExchange(item.edge, item.id);
        return;
      }
      usedCommunications.add(match.id);
      renderRoutedExchange(item.edge, item.id, match, geometry);
    });

    communications.forEach(item => {
      if (!usedCommunications.has(item.id)) ensureCommunicationRendered(item.edge, item.id, communicationGeometries);
    });

    indexed.forEach(item => renderOrdinary(item.edge, item.id));
    updateSelection();
  }

  function scheduleEdgeRender() {
    if (state.edgeRenderFrame) return;
    state.edgeRenderFrame = requestAnimationFrame(() => {
      state.edgeRenderFrame = 0;
      renderEdges();
    });
  }

  function render() {
    if (!init()) return;
    const hasNodes = [...state.byId.values()].some(isVisibleNode);
    el.empty.hidden = hasNodes;
    el.scene.hidden = !hasNodes;
    if (!hasNodes) {
      state.selected.clear();
      updateSelection();
      return;
    }
    updateBounds();
    renderNodes();
    renderEdges();
    applyView();
    updateCapabilitiesButton();
  }

  function focusForManipulation(id, event) {
    if (state.mode !== 'normal') return;
    if (!(event.ctrlKey || event.metaKey)) state.selected.clear();
    state.selected.add(selectionKey('node', id));
    updateSelection();
  }

  function beginMove(event, id) {
    if (event.button !== 0 || event.target.closest('.oa-diagram-resize-handle')) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    focusForManipulation(id, event);
    state.drag = {
      kind: 'move',
      id,
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      ax: 0,
      ay: 0,
      moved: false,
    };
    el.viewport.classList.add('is-dragging');
    event.preventDefault();
  }

  function beginResize(event, id) {
    if (event.button !== 0) return;
    event.stopPropagation();
    const position = state.layout.get(id);
    if (!position) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    focusForManipulation(id, event);
    state.drag = {
      kind: 'resize',
      id,
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      w: position.w,
      h: position.h,
      moved: false,
    };
    el.viewport.classList.add('is-dragging');
    event.preventDefault();
  }

  function beginPan(event) {
    if (event.button !== 0 || event.target.closest('.oa-diagram-node, .oa-diagram-port, .oa-diagram-edge, .oa-diagram-edge-label')) return;
    state.drag = {
      kind: 'pan',
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      vx: state.view.x,
      vy: state.view.y,
      moved: false,
    };
    el.viewport.setPointerCapture?.(event.pointerId);
    el.viewport.classList.add('is-panning');
    event.preventDefault();
  }

  function updateNode(id) {
    const position = state.layout.get(id);
    const node = el.scene.querySelector(`[data-node-id="${CSS.escape(id)}"]`);
    if (!position || !node) return;
    Object.assign(node.style, {
      left: `${position.x}px`,
      top: `${position.y}px`,
      width: `${position.w}px`,
      height: `${position.h}px`,
    });
  }

  function onPointerMove(event) {
    const drag = state.drag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const px = event.clientX - drag.x;
    const py = event.clientY - drag.y;
    drag.moved ||= Math.abs(px) + Math.abs(py) > 3;

    if (drag.kind === 'pan') {
      state.view.x = drag.vx + px;
      state.view.y = drag.vy + py;
      applyView();
      return;
    }

    const dx = px / state.view.zoom;
    const dy = py / state.view.zoom;
    if (drag.kind === 'move') {
      const stepX = dx - drag.ax;
      const stepY = dy - drag.ay;
      drag.ax = dx;
      drag.ay = dy;
      moveSubtree(drag.id, stepX, stepY);
      constrainOrExpandParent(drag.id);
      scheduleEdgeRender();
      return;
    }

    if (drag.kind === 'resize') {
      const position = state.layout.get(drag.id);
      if (!position) return;
      const node = state.byId.get(drag.id);
      const required = requiredContainerSize(drag.id);
      const [baseW, baseH] = minFor(node?.type);
      position.w = Math.max(baseW, required.w, drag.w + dx);
      position.h = Math.max(baseH, required.h, drag.h + dy);
      updateNode(drag.id);
      constrainOrExpandParent(drag.id);
      scheduleEdgeRender();
    }
  }

  function endPointer(event) {
    const drag = state.drag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (drag.moved) state.suppressClickUntil = Date.now() + 140;
    state.drag = null;
    el.viewport.classList.remove('is-panning', 'is-dragging');
    if (state.edgeRenderFrame) {
      cancelAnimationFrame(state.edgeRenderFrame);
      state.edgeRenderFrame = 0;
    }
    updateBounds();
    renderEdges();
    persist();
  }

  function zoom(factor, clientX = null, clientY = null) {
    const rect = el.viewport.getBoundingClientRect();
    const old = state.view.zoom;
    const next = Math.max(0.25, Math.min(2.5, old * factor));
    const px = clientX == null ? rect.width / 2 : clientX - rect.left;
    const py = clientY == null ? rect.height / 2 : clientY - rect.top;
    const sx = (px - state.view.x) / old;
    const sy = (py - state.view.y) / old;
    state.view.zoom = next;
    state.view.x = px - sx * next;
    state.view.y = py - sy * next;
    applyView();
    persist();
  }

  function fitView(persistView = true) {
    const visible = visibleLayout();
    if (!visible.length) return;
    const rect = el.viewport.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    visible.forEach(([, position]) => {
      minX = Math.min(minX, position.x);
      minY = Math.min(minY, position.y);
      maxX = Math.max(maxX, position.x + position.w);
      maxY = Math.max(maxY, position.y + position.h);
    });
    const width = Math.max(1, maxX - minX);
    const height = Math.max(1, maxY - minY);
    const pad = 32;
    const z = Math.max(0.25, Math.min(1.25, (rect.width - pad * 2) / width, (rect.height - pad * 2) / height));
    state.view = {
      x: (rect.width - width * z) / 2 - minX * z,
      y: (rect.height - height * z) / 2 - minY * z,
      zoom: z,
    };
    applyView();
    if (persistView) persist();
  }

  function resetLayout() {
    const showCapabilities = state.showCapabilities;
    try {
      localStorage.removeItem(storageKey());
    } catch (_error) {
      // Ignore storage failures.
    }
    state.showCapabilities = showCapabilities;
    state.view = {x: 28, y: 28, zoom: 1};
    autoLayout();
    render();
    persist();
    requestAnimationFrame(() => fitView());
  }

  function setMode(mode) {
    state.mode = mode === 'scenario' ? 'scenario' : 'normal';
    state.selected.clear();
    if (el.mode) el.mode.textContent = state.mode === 'scenario' ? 'Scenario selection' : 'Normal selection';
    el.tab?.classList.toggle('scenario-mode', state.mode === 'scenario');
    updateSelection();
  }

  function setModel(model, session) {
    const nextModel = model || {nodes: [], drafts: [], edges: []};
    const nextSession = clean(session) || 'default';
    const nextSignature = modelSignature(nextModel);
    const sessionChanged = nextSession !== state.session;

    // API polling returns the same model repeatedly. Rebuilding auto-layout on
    // every poll used to fight pointer movement and made manual drag feel stuck.
    if (!sessionChanged && state.modelSignature === nextSignature) {
      state.model = nextModel;
      return;
    }

    if (sessionChanged) {
      state.session = nextSession;
      state.view = {x: 28, y: 28, zoom: 1};
      state.selected.clear();
      state.modelSignature = '';
      const saved = loadSaved();
      state.showCapabilities = saved.showCapabilities !== false;
    }

    state.model = nextModel;
    state.modelSignature = nextSignature;
    buildModel(state.model);
    autoLayout();
    render();
    persist();
  }

  init();
  if (typeof applyState === 'function') {
    const priorApplyState = applyState;
    applyState = function applyStateWithOperationalDiagram(nextState) {
      priorApplyState(nextState);
      setModel(nextState?.model || {}, nextState?.session_id || state.session);
    };
  }

  window.oaDiagram = Object.freeze({
    setMode,
    getSelection: selectionPayload,
    clearSelection() {
      state.selected.clear();
      updateSelection();
    },
    fitView,
    resetLayout,
    setCapabilitiesVisible(value) {
      state.showCapabilities = Boolean(value);
      updateCapabilitiesButton();
      render();
      persist();
    },
    render(model, session = state.session) {
      setModel(model, session);
    },
  });
})();
