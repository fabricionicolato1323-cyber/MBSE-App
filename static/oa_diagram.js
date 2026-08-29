(() => {
  'use strict';

  const PARTICIPANTS = new Set(['OperationalEntity', 'OperationalActor']);
  const MIN = {
    OperationalEntity: [270, 160],
    OperationalActor: [230, 145],
    OperationalActivity: [170, 64],
    OperationalCapability: [190, 66],
    Pending: [170, 64],
  };
  const PAD = 18;
  const HEADER = 46;
  const GAP = 14;
  const SVG_NS = 'http://www.w3.org/2000/svg';

  const state = {
    session: 'default',
    model: {nodes: [], drafts: [], edges: []},
    byId: new Map(),
    parent: new Map(),
    children: new Map(),
    layout: new Map(),
    invalidContainments: [],
    selected: new Set(),
    mode: 'normal',
    view: {x: 28, y: 28, zoom: 1},
    drag: null,
    suppressClickUntil: 0,
    ready: false,
  };

  const el = {};

  const clean = value => String(value ?? '').replace(/\s+/g, ' ').trim();
  const minFor = type => MIN[type] || [170, 64];
  const typeName = type => ({
    OperationalEntity: 'Operational Entity',
    OperationalActor: 'Operational Actor',
    OperationalActivity: 'Operational Activity',
    OperationalCapability: 'Operational Capability',
    Pending: 'Temporary input',
  })[type] || clean(type) || 'Model element';
  const selectionKey = (kind, id) => `${kind}:${id}`;
  const storageKey = () => `oa-diagram-layout:${state.session}`;

  function validContainment(parent, child) {
    if (!parent || !child) return false;
    if (parent.type === 'OperationalEntity') return PARTICIPANTS.has(child.type);
    if (parent.type === 'OperationalActor') return child.type === 'OperationalActor';
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
      </div>
      <span id="oaDiagramMode" class="oa-diagram-mode-label">Normal selection</span>`;

    const viewport = document.createElement('div');
    viewport.id = 'oaDiagramViewport';
    viewport.className = 'oa-diagram-viewport';
    viewport.tabIndex = 0;
    viewport.setAttribute('aria-label', 'Interactive Operational Analysis diagram');
    viewport.innerHTML = `
      <div id="oaDiagramScene" class="oa-diagram-scene">
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

  function init() {
    if (state.ready) return true;
    installMarkup();
    Object.assign(el, {
      tab: document.getElementById('diagramTab'),
      viewport: document.getElementById('oaDiagramViewport'),
      scene: document.getElementById('oaDiagramScene'),
      edges: document.getElementById('oaDiagramEdges'),
      nodes: document.getElementById('oaDiagramNodes'),
      ports: document.getElementById('oaDiagramPorts'),
      empty: document.getElementById('oaDiagramEmpty'),
      status: document.getElementById('oaDiagramStatus'),
      mode: document.getElementById('oaDiagramMode'),
    });
    if (!el.tab || !el.viewport || !el.scene || !el.edges || !el.nodes || !el.ports) return false;

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
    document.querySelector('[data-tab="diagram"]')?.addEventListener('click', () => requestAnimationFrame(() => {
      renderEdges();
      if (!loadSaved().view) fitView(false);
    }));
    return true;
  }

  function buildModel(model) {
    const nodes = [...(model.nodes || []), ...(model.drafts || [])];
    const edges = model.edges || [];
    state.byId = new Map(nodes.map(node => [node.id, node]));
    state.parent = new Map();
    state.children = new Map();
    state.invalidContainments = [];

    const addParent = (child, parent) => {
      if (!child || !parent || child === parent || state.parent.has(child)) return;
      state.parent.set(child, parent);
      if (!state.children.has(parent)) state.children.set(parent, []);
      state.children.get(parent).push(child);
    };

    edges.filter(edge => edge.type === 'CONTAINS').forEach(edge => {
      const parent = state.byId.get(edge.source);
      const child = state.byId.get(edge.target);
      if (!PARTICIPANTS.has(parent?.type) || !PARTICIPANTS.has(child?.type)) return;
      if (!validContainment(parent, child)) {
        state.invalidContainments.push(edge);
        return;
      }
      addParent(child.id, parent.id);
    });

    edges.filter(edge => edge.type === 'PERFORMS').forEach(edge => {
      const parent = state.byId.get(edge.source);
      const child = state.byId.get(edge.target);
      if (PARTICIPANTS.has(parent?.type) && child?.type === 'OperationalActivity') addParent(child.id, parent.id);
    });
  }

  function childNodes(id, predicate = () => true) {
    return (state.children.get(id) || []).map(child => state.byId.get(child)).filter(node => node && predicate(node));
  }

  function measureParticipant(id, seen = new Set()) {
    const node = state.byId.get(id);
    const [minW, minH] = minFor(node?.type);
    if (!node || seen.has(id)) return {w: minW, h: minH};
    const next = new Set(seen); next.add(id);
    let w = minW;
    let h = HEADER + PAD;
    for (const activity of childNodes(id, child => child.type === 'OperationalActivity')) {
      const [cw, ch] = minFor(activity.type);
      w = Math.max(w, cw + PAD * 2);
      h += ch + GAP;
    }
    for (const participant of childNodes(id, child => PARTICIPANTS.has(child.type))) {
      const child = measureParticipant(participant.id, next);
      w = Math.max(w, child.w + PAD * 2);
      h += child.h + GAP;
    }
    return {w, h: Math.max(minH, h + PAD - GAP)};
  }

  function put(id, x, y, w, h) {
    const [minW, minH] = minFor(state.byId.get(id)?.type);
    state.layout.set(id, {x, y, w: Math.max(minW, w), h: Math.max(minH, h)});
  }

  function placeParticipant(id, x, y, seen = new Set()) {
    if (seen.has(id)) return;
    const next = new Set(seen); next.add(id);
    const size = measureParticipant(id, next);
    put(id, x, y, size.w, size.h);
    let cursor = y + HEADER + PAD;
    for (const activity of childNodes(id, child => child.type === 'OperationalActivity')) {
      const [w, h] = minFor(activity.type);
      put(activity.id, x + PAD, cursor, Math.min(w, size.w - PAD * 2), h);
      cursor += h + GAP;
    }
    for (const participant of childNodes(id, child => PARTICIPANTS.has(child.type))) {
      const child = measureParticipant(participant.id, next);
      placeParticipant(participant.id, x + PAD, cursor, next);
      cursor += child.h + GAP;
    }
  }

  function autoLayout() {
    state.layout = new Map();
    const roots = [...state.byId.values()].filter(node => !state.parent.has(node.id));
    let x = 60, y = 60, rowH = 0;
    for (const node of roots) {
      let w, h;
      if (PARTICIPANTS.has(node.type)) {
        const size = measureParticipant(node.id);
        w = size.w; h = size.h;
        placeParticipant(node.id, x, y);
      } else {
        [w, h] = minFor(node.type);
        put(node.id, x, y, w, h);
      }
      if (x + w > 1350) { x = 60; y += rowH + 70; rowH = 0; }
      else { x += w + 70; rowH = Math.max(rowH, h); }
    }
    applySaved();
  }

  function loadSaved() {
    try { return JSON.parse(localStorage.getItem(storageKey()) || '{}') || {}; }
    catch (_error) { return {}; }
  }

  function applySaved() {
    const saved = loadSaved();
    for (const [id, value] of Object.entries(saved.nodes || {})) {
      if (!state.layout.has(id)) continue;
      const [minW, minH] = minFor(state.byId.get(id)?.type);
      state.layout.set(id, {
        x: Number.isFinite(value.x) ? value.x : state.layout.get(id).x,
        y: Number.isFinite(value.y) ? value.y : state.layout.get(id).y,
        w: Math.max(minW, Number(value.w) || state.layout.get(id).w),
        h: Math.max(minH, Number(value.h) || state.layout.get(id).h),
      });
    }
    if (saved.view && Number.isFinite(saved.view.zoom)) state.view = saved.view;
  }

  function persist() {
    const nodes = {};
    state.layout.forEach((v, id) => { nodes[id] = {x: v.x, y: v.y, w: v.w, h: v.h}; });
    try { localStorage.setItem(storageKey(), JSON.stringify({nodes, view: state.view})); }
    catch (_error) { /* persistence is optional */ }
  }

  function descendants(id, result = []) {
    for (const child of state.children.get(id) || []) { result.push(child); descendants(child, result); }
    return result;
  }

  function center(id) {
    const p = state.layout.get(id);
    return p ? {x: p.x + p.w / 2, y: p.y + p.h / 2} : null;
  }

  function updateBounds() {
    let maxX = 1200, maxY = 800;
    state.layout.forEach(p => { maxX = Math.max(maxX, p.x + p.w + 120); maxY = Math.max(maxY, p.y + p.h + 120); });
    el.scene.style.width = `${maxX}px`; el.scene.style.height = `${maxY}px`;
    el.edges.setAttribute('width', String(maxX)); el.edges.setAttribute('height', String(maxY));
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
    if (additive && state.selected.has(key)) state.selected.delete(key); else state.selected.add(key);
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
      else el.status.textContent = state.mode === 'scenario' ? 'Scenario selection mode: click elements to add or remove them.' : 'Click an element to select it. Ctrl/Cmd-click keeps multiple elements selected.';
    }
    window.dispatchEvent(new CustomEvent('oa:diagram-selection-change', {detail: {mode: state.mode, selected}}));
  }

  function nodeElement(node) {
    const p = state.layout.get(node.id);
    const div = document.createElement('div');
    div.className = `oa-diagram-node type-${clean(node.type).toLowerCase()} ${node.status === 'temporary' ? 'temporary' : 'confirmed'} ${PARTICIPANTS.has(node.type) ? 'participant-container' : 'leaf-node'}`;
    div.dataset.nodeId = node.id;
    div.dataset.oaSelectKey = selectionKey('node', node.id);
    div.tabIndex = 0; div.setAttribute('role', 'button'); div.setAttribute('aria-pressed', 'false');
    Object.assign(div.style, {left: `${p.x}px`, top: `${p.y}px`, width: `${p.w}px`, height: `${p.h}px`});
    div.innerHTML = `<div class="oa-diagram-node-header"><span class="oa-diagram-node-type">${typeName(node.type)}</span><strong class="oa-diagram-node-title">${clean(node.name || node.id)}</strong></div>`;
    if (PARTICIPANTS.has(node.type)) {
      const hint = document.createElement('small');
      hint.className = 'oa-diagram-containment-hint';
      hint.textContent = node.type === 'OperationalActor' ? 'actors + activities' : 'entities + actors + activities';
      div.appendChild(hint);
    }
    const resize = document.createElement('button');
    resize.type = 'button'; resize.className = 'oa-diagram-resize-handle'; resize.textContent = '↘';
    resize.setAttribute('aria-label', `Resize ${clean(node.name || node.id)}`);
    resize.addEventListener('pointerdown', event => beginResize(event, node.id));
    div.appendChild(resize);
    div.addEventListener('pointerdown', event => beginMove(event, node.id));
    div.addEventListener('click', event => { if (!event.target.closest('.oa-diagram-resize-handle')) select('node', node.id, event); });
    div.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select('node', node.id, event); } });
    return div;
  }

  function renderNodes() {
    el.nodes.innerHTML = '';
    const nodes = [...state.byId.values()].sort((a, b) => depth(a.id) - depth(b.id));
    nodes.forEach(node => el.nodes.appendChild(nodeElement(node)));
  }

  function depth(id) {
    let d = 0, p = state.parent.get(id); const seen = new Set();
    while (p && !seen.has(p)) { seen.add(p); d += 1; p = state.parent.get(p); }
    return d;
  }

  function svg(name, attrs = {}) {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  }

  function curve(a, b) {
    const bend = Math.max(45, Math.abs(b.x - a.x) * .4), dir = b.x >= a.x ? 1 : -1;
    return `M ${a.x} ${a.y} C ${a.x + bend * dir} ${a.y}, ${b.x - bend * dir} ${b.y}, ${b.x} ${b.y}`;
  }

  function anchor(id, toward) {
    const p = state.layout.get(id), c = center(id), t = center(toward);
    if (!p || !c || !t) return null;
    if (Math.abs(t.x - c.x) >= Math.abs(t.y - c.y)) return {x: t.x >= c.x ? p.x + p.w : p.x, y: c.y};
    return {x: c.x, y: t.y >= c.y ? p.y + p.h : p.y};
  }

  function edgeId(edge, i) { return clean(edge.id) || `${edge.type}:${edge.source}:${edge.target}:${clean(edge.name)}:${i}`; }

  function addEdgeInteraction(node, id) {
    node.dataset.oaSelectKey = selectionKey('edge', id); node.setAttribute('role', 'button'); node.setAttribute('tabindex', '0'); node.setAttribute('aria-pressed', 'false');
    node.addEventListener('click', event => { event.stopPropagation(); select('edge', id, event); });
    node.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select('edge', id, event); } });
  }

  function addPort(id, participantId, x, y) {
    const port = document.createElement('button');
    port.type = 'button'; port.className = 'oa-diagram-port'; port.textContent = 'P';
    port.dataset.oaSelectKey = selectionKey('port', id); port.setAttribute('aria-pressed', 'false');
    Object.assign(port.style, {left: `${x - 10}px`, top: `${y - 10}px`});
    port.setAttribute('aria-label', `Communication port on ${clean(state.byId.get(participantId)?.name || participantId)}`);
    port.addEventListener('click', event => { event.stopPropagation(); select('port', id, event); });
    el.ports.appendChild(port);
  }

  function renderCommunication(edge, id) {
    if (!PARTICIPANTS.has(state.byId.get(edge.source)?.type) || !PARTICIPANTS.has(state.byId.get(edge.target)?.type)) return;
    const a = anchor(edge.source, edge.target), b = anchor(edge.target, edge.source);
    if (!a || !b) return;
    const path = svg('path', {d: curve(a, b), class: 'oa-diagram-edge communication-mean'});
    addEdgeInteraction(path, id); el.edges.appendChild(path);
    addPort(`${id}:source`, edge.source, a.x, a.y); addPort(`${id}:target`, edge.target, b.x, b.y);
    const label = svg('text', {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 9, class: 'oa-diagram-edge-label communication-label'});
    label.textContent = clean(edge.name) || 'Communication mean'; addEdgeInteraction(label, id); el.edges.appendChild(label);
  }

  function renderOrdinary(edge, id) {
    if (['CONTAINS', 'PERFORMS', 'LOCATED_IN', 'COMMUNICATION_MEAN'].includes(edge.type)) return;
    const a = anchor(edge.source, edge.target), b = anchor(edge.target, edge.source);
    if (!a || !b) return;
    const path = svg('path', {d: curve(a, b), class: `oa-diagram-edge ${edge.type === 'OPERATIONAL_EXCHANGE' ? 'operational-exchange' : 'ordinary-relation'}`, 'marker-end': 'url(#oaArrow)'});
    addEdgeInteraction(path, id); el.edges.appendChild(path);
    const label = svg('text', {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 7, class: 'oa-diagram-edge-label'});
    label.textContent = clean(edge.name) || clean(edge.type).toLowerCase().replaceAll('_', ' '); addEdgeInteraction(label, id); el.edges.appendChild(label);
  }

  function renderEdges() {
    if (!state.ready) return;
    el.edges.innerHTML = '<defs><marker id="oaArrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="oa-diagram-arrow-head"></path></marker></defs>';
    el.ports.innerHTML = '';
    (state.model.edges || []).forEach((edge, i) => {
      const id = edgeId(edge, i);
      if (edge.type === 'COMMUNICATION_MEAN') renderCommunication(edge, id); else renderOrdinary(edge, id);
    });
    updateSelection();
  }

  function render() {
    if (!init()) return;
    const hasNodes = state.byId.size > 0;
    el.empty.hidden = hasNodes; el.scene.hidden = !hasNodes;
    if (!hasNodes) { state.selected.clear(); updateSelection(); return; }
    updateBounds(); renderNodes(); renderEdges(); applyView();
  }

  function focusForManipulation(id, event) {
    if (state.mode !== 'normal') return;
    if (!(event.ctrlKey || event.metaKey)) state.selected.clear();
    state.selected.add(selectionKey('node', id)); updateSelection();
  }

  function beginMove(event, id) {
    if (event.button !== 0 || event.target.closest('.oa-diagram-resize-handle')) return;
    event.currentTarget.setPointerCapture?.(event.pointerId); focusForManipulation(id, event);
    state.drag = {kind: 'move', id, pointerId: event.pointerId, x: event.clientX, y: event.clientY, ax: 0, ay: 0, moved: false};
    event.preventDefault();
  }

  function beginResize(event, id) {
    if (event.button !== 0) return;
    event.stopPropagation(); const p = state.layout.get(id); if (!p) return;
    event.currentTarget.setPointerCapture?.(event.pointerId); focusForManipulation(id, event);
    state.drag = {kind: 'resize', id, pointerId: event.pointerId, x: event.clientX, y: event.clientY, w: p.w, h: p.h, moved: false};
    event.preventDefault();
  }

  function beginPan(event) {
    if (event.button !== 0 || event.target.closest('.oa-diagram-node, .oa-diagram-port, .oa-diagram-edge, .oa-diagram-edge-label')) return;
    state.drag = {kind: 'pan', pointerId: event.pointerId, x: event.clientX, y: event.clientY, vx: state.view.x, vy: state.view.y, moved: false};
    el.viewport.setPointerCapture?.(event.pointerId); el.viewport.classList.add('is-panning'); event.preventDefault();
  }

  function updateNode(id) {
    const p = state.layout.get(id), node = el.nodes.querySelector(`[data-node-id="${CSS.escape(id)}"]`); if (!p || !node) return;
    Object.assign(node.style, {left: `${p.x}px`, top: `${p.y}px`, width: `${p.w}px`, height: `${p.h}px`});
  }

  function onPointerMove(event) {
    const d = state.drag; if (!d || d.pointerId !== event.pointerId) return;
    const px = event.clientX - d.x, py = event.clientY - d.y; d.moved ||= Math.abs(px) + Math.abs(py) > 3;
    if (d.kind === 'pan') { state.view.x = d.vx + px; state.view.y = d.vy + py; applyView(); return; }
    const dx = px / state.view.zoom, dy = py / state.view.zoom;
    if (d.kind === 'move') {
      const stepX = dx - d.ax, stepY = dy - d.ay; d.ax = dx; d.ay = dy;
      for (const id of [d.id, ...descendants(d.id)]) { const p = state.layout.get(id); if (p) { p.x += stepX; p.y += stepY; updateNode(id); } }
      clampToParent(d.id); renderEdges();
    } else if (d.kind === 'resize') {
      const p = state.layout.get(d.id), [mw, mh] = minFor(state.byId.get(d.id)?.type); if (!p) return;
      p.w = Math.max(mw, d.w + dx); p.h = Math.max(mh, d.h + dy); updateNode(d.id); renderEdges();
    }
  }

  function clampToParent(id) {
    const p = state.layout.get(id), owner = state.layout.get(state.parent.get(id)); if (!p || !owner) return;
    const minX = owner.x + PAD, minY = owner.y + HEADER;
    const maxX = Math.max(minX, owner.x + owner.w - PAD - p.w);
    const maxY = Math.max(minY, owner.y + owner.h - PAD - p.h);
    p.x = Math.max(minX, Math.min(p.x, maxX));
    p.y = Math.max(minY, Math.min(p.y, maxY));
    updateNode(id);
  }

  function endPointer(event) {
    const d = state.drag; if (!d || d.pointerId !== event.pointerId) return;
    if (d.moved) state.suppressClickUntil = Date.now() + 120;
    state.drag = null; el.viewport.classList.remove('is-panning'); updateBounds(); renderEdges(); persist();
  }

  function zoom(factor, clientX = null, clientY = null) {
    const rect = el.viewport.getBoundingClientRect(), old = state.view.zoom, next = Math.max(.25, Math.min(2.5, old * factor));
    const px = clientX == null ? rect.width / 2 : clientX - rect.left, py = clientY == null ? rect.height / 2 : clientY - rect.top;
    const sx = (px - state.view.x) / old, sy = (py - state.view.y) / old;
    state.view.zoom = next; state.view.x = px - sx * next; state.view.y = py - sy * next; applyView(); persist();
  }

  function fitView(persistView = true) {
    if (!state.layout.size) return;
    const rect = el.viewport.getBoundingClientRect(); if (!rect.width || !rect.height) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    state.layout.forEach(p => { minX = Math.min(minX, p.x); minY = Math.min(minY, p.y); maxX = Math.max(maxX, p.x + p.w); maxY = Math.max(maxY, p.y + p.h); });
    const w = Math.max(1, maxX - minX), h = Math.max(1, maxY - minY), pad = 32;
    const z = Math.max(.25, Math.min(1.25, (rect.width - pad * 2) / w, (rect.height - pad * 2) / h));
    state.view = {x: (rect.width - w * z) / 2 - minX * z, y: (rect.height - h * z) / 2 - minY * z, zoom: z}; applyView();
    if (persistView) persist();
  }

  function resetLayout() {
    try { localStorage.removeItem(storageKey()); } catch (_error) {}
    state.view = {x: 28, y: 28, zoom: 1}; autoLayout(); render(); requestAnimationFrame(() => fitView());
  }

  function setMode(mode) {
    state.mode = mode === 'scenario' ? 'scenario' : 'normal'; state.selected.clear();
    if (el.mode) el.mode.textContent = state.mode === 'scenario' ? 'Scenario selection' : 'Normal selection';
    el.tab?.classList.toggle('scenario-mode', state.mode === 'scenario'); updateSelection();
  }

  function setModel(model, session) {
    const nextSession = clean(session) || 'default';
    if (nextSession !== state.session) { state.session = nextSession; state.view = {x: 28, y: 28, zoom: 1}; state.selected.clear(); }
    state.model = model || {nodes: [], drafts: [], edges: []}; buildModel(state.model); autoLayout(); render();
  }

  init();
  if (typeof applyState === 'function') {
    const priorApplyState = applyState;
    applyState = function applyStateWithOperationalDiagram(nextState) {
      priorApplyState(nextState); setModel(nextState?.model || {}, nextState?.session_id || state.session);
    };
  }

  window.oaDiagram = Object.freeze({
    setMode,
    getSelection: selectionPayload,
    clearSelection() { state.selected.clear(); updateSelection(); },
    fitView,
    resetLayout,
    render(model, session = state.session) { setModel(model, session); },
  });
})();
