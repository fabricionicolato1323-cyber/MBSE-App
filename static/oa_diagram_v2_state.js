export const PARTICIPANTS = new Set(['OperationalEntity', 'OperationalActor']);
export const MIN = {
  OperationalEntity: [300, 190], OperationalActor: [260, 175],
  OperationalActivity: [190, 72], OperationalCapability: [210, 76], Pending: [180, 68],
};
export const PAD = 22, HEADER = 54, GAP = 18, PARTICIPANT_GAP = 24, LAYOUT_VERSION = 3;
const MAX_NESTED_ROW_WIDTH = 960;

export const state = {
  session: 'default', model: {nodes: [], drafts: [], edges: []}, modelSignature: '',
  byId: new Map(), parent: new Map(), parentRelation: new Map(), children: new Map(), performersByActivity: new Map(),
  communicationMeans: [], layout: new Map(), invalidContainments: [], selected: new Set(),
  mode: 'normal', showCapabilities: true, view: {x: 28, y: 28, zoom: 1},
  drag: null, suppressClickUntil: 0, ready: false,
};

export const clean = value => String(value ?? '').replace(/\s+/g, ' ').trim();
export const minFor = type => MIN[type] || [180, 68];
export const typeName = type => ({
  OperationalEntity: 'Operational Entity', OperationalActor: 'Operational Actor',
  OperationalActivity: 'Operational Activity', OperationalCapability: 'Operational Capability',
  Pending: 'Temporary input',
})[type] || clean(type) || 'Model element';
export const selectionKey = (kind, id) => `${kind}:${id}`;
export const edgeId = (edge, i) => clean(edge.id) || clean(edge.key) || `${edge.type}:${edge.source}:${edge.target}:${clean(edge.name)}:${i}`;
export const storageKey = () => `oa-diagram-layout:v${LAYOUT_VERSION}:${state.session}`;

function canonicalModelValue(value) {
  if (Array.isArray(value)) return value.map(canonicalModelValue);
  if (value && typeof value === 'object') {
    const result = {};
    Object.keys(value).sort().forEach(key => { result[key] = canonicalModelValue(value[key]); });
    return result;
  }
  return value;
}

function canonicalModelCollection(items) {
  return (Array.isArray(items) ? items : [])
    .map(item => canonicalModelValue(item))
    .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
}

export function signatureForModel(model) {
  // The diagram must react to every persisted element change, including future
  // attributes that the renderer may learn to use. Keep this generic instead
  // of maintaining a hardcoded allow-list such as name/exchange_refs.
  return JSON.stringify({
    nodes: canonicalModelCollection(model?.nodes),
    drafts: canonicalModelCollection(model?.drafts),
    edges: canonicalModelCollection(model?.edges),
  });
}

export function validContainment(parent, child) {
  if (!parent || !child) return false;
  if (parent.type === 'OperationalEntity') return PARTICIPANTS.has(child.type);
  if (parent.type === 'OperationalActor') return child.type === 'OperationalActor';
  return false;
}

export function validVisualLocation(parent, child) {
  return parent?.type === 'OperationalEntity' && PARTICIPANTS.has(child?.type);
}

export const isVisibleNode = node => !!node && (state.showCapabilities || node.type !== 'OperationalCapability');
export const visibleLayoutEntries = () => [...state.layout.entries()].filter(([id]) => isVisibleNode(state.byId.get(id)));

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

export function buildModel(model) {
  const nodes = [...(model.nodes || []), ...(model.drafts || [])], edges = model.edges || [];
  state.byId = new Map(nodes.map(node => [node.id, node]));
  state.parent = new Map(); state.parentRelation = new Map(); state.children = new Map(); state.performersByActivity = new Map();
  state.communicationMeans = []; state.invalidContainments = [];

  const addParent = (child, parent, relation) => {
    if (!child || !parent || child === parent || state.parent.has(child) || wouldCreateVisualCycle(child, parent)) return false;
    state.parent.set(child, parent); state.parentRelation.set(child, relation);
    if (!state.children.has(parent)) state.children.set(parent, []);
    state.children.get(parent).push(child);
    return true;
  };

  // Structural composition has precedence over location when both exist.
  edges.filter(edge => edge.type === 'CONTAINS').forEach(edge => {
    const parent = state.byId.get(edge.source), child = state.byId.get(edge.target);
    if (!PARTICIPANTS.has(parent?.type) || !PARTICIPANTS.has(child?.type)) return;
    if (!validContainment(parent, child)) { state.invalidContainments.push(edge); return; }
    addParent(child.id, parent.id, 'CONTAINS');
  });

  // Match the textual view: LOCATED_IN may create visual enclosure while the
  // semantic edge remains LOCATED_IN. This is what lets an environment/context
  // entity embrace the participants operating in it without rewriting facts.
  edges.filter(edge => edge.type === 'LOCATED_IN').forEach(edge => {
    const child = state.byId.get(edge.source), parent = state.byId.get(edge.target);
    if (state.parent.has(child?.id) || !validVisualLocation(parent, child)) return;
    addParent(child.id, parent.id, 'LOCATED_IN');
  });

  edges.filter(edge => edge.type === 'PERFORMS').forEach(edge => {
    const performer = state.byId.get(edge.source), activity = state.byId.get(edge.target);
    if (!PARTICIPANTS.has(performer?.type) || activity?.type !== 'OperationalActivity') return;
    if (!state.performersByActivity.has(activity.id)) state.performersByActivity.set(activity.id, []);
    state.performersByActivity.get(activity.id).push(performer.id);
    // The first confirmed performer owns the visual enclosure. Additional
    // performers remain semantic relationships but do not duplicate the block.
    addParent(activity.id, performer.id, 'PERFORMS');
  });

  state.communicationMeans = edges.map((edge, i) => ({...edge, _diagramId: edgeId(edge, i)}))
    .filter(edge => edge.type === 'COMMUNICATION_MEAN');
}

export function childNodes(id, predicate = () => true) {
  return (state.children.get(id) || []).map(child => state.byId.get(child)).filter(node => node && predicate(node));
}

export function depth(id) {
  let d = 0, parent = state.parent.get(id); const seen = new Set();
  while (parent && !seen.has(parent)) { seen.add(parent); d += 1; parent = state.parent.get(parent); }
  return d;
}

function packParticipantRows(items) {
  const rows = [];
  let row = {items: [], width: 0, height: 0};
  for (const item of items) {
    const gap = row.items.length ? PARTICIPANT_GAP : 0;
    if (row.items.length && row.width + gap + item.size.w > MAX_NESTED_ROW_WIDTH) {
      rows.push(row); row = {items: [], width: 0, height: 0};
    }
    const nextGap = row.items.length ? PARTICIPANT_GAP : 0;
    row.items.push(item); row.width += nextGap + item.size.w; row.height = Math.max(row.height, item.size.h);
  }
  if (row.items.length) rows.push(row);
  return rows;
}

export function measureParticipant(id, seen = new Set()) {
  const node = state.byId.get(id), [minW, minH] = minFor(node?.type);
  if (!node || seen.has(id)) return {w: minW, h: minH};
  const next = new Set(seen); next.add(id);
  const activities = childNodes(id, child => child.type === 'OperationalActivity');
  const participants = childNodes(id, child => PARTICIPANTS.has(child.type));

  let activityW = 0, activityH = 0;
  for (const activity of activities) {
    const [cw, ch] = minFor(activity.type); activityW = Math.max(activityW, cw); activityH += ch + (activityH ? GAP : 0);
  }

  const participantItems = participants.map(child => ({id: child.id, size: measureParticipant(child.id, next)}));
  const rows = packParticipantRows(participantItems);
  const participantW = rows.length ? Math.max(...rows.map(row => row.width)) : 0;
  const participantH = rows.reduce((sum, row, index) => sum + row.height + (index ? PARTICIPANT_GAP : 0), 0);
  const contentW = Math.max(activityW, participantW);
  const sections = [activityH, participantH].filter(Boolean);
  const contentH = sections.reduce((sum, value) => sum + value, 0) + Math.max(0, sections.length - 1) * GAP;
  return {w: Math.max(minW, contentW + PAD * 2), h: Math.max(minH, HEADER + PAD + contentH + PAD)};
}

function put(id, x, y, w, h) {
  const [minW, minH] = minFor(state.byId.get(id)?.type);
  state.layout.set(id, {x, y, w: Math.max(minW, w), h: Math.max(minH, h)});
}

function placeParticipant(id, x, y, seen = new Set()) {
  if (seen.has(id)) return;

  // IMPORTANT: measure with the incoming guard, not a guard that already
  // contains this id. Measuring with `next` collapsed every container to its
  // minimum size and was the root cause of children appearing outside parents.
  const size = measureParticipant(id, seen);
  const next = new Set(seen); next.add(id); put(id, x, y, size.w, size.h);
  const activities = childNodes(id, child => child.type === 'OperationalActivity');
  const participants = childNodes(id, child => PARTICIPANTS.has(child.type));

  let cursorY = y + HEADER + PAD;
  for (const activity of activities) {
    const [, h] = minFor(activity.type);
    put(activity.id, x + PAD, cursorY, Math.max(minFor(activity.type)[0], size.w - PAD * 2), h);
    cursorY += h + GAP;
  }
  if (activities.length) cursorY -= GAP;

  const participantItems = participants.map(child => ({id: child.id, size: measureParticipant(child.id, next)}));
  const rows = packParticipantRows(participantItems);
  if (activities.length && rows.length) cursorY += GAP;
  rows.forEach((row, rowIndex) => {
    let cursorX = x + PAD;
    row.items.forEach(item => {
      placeParticipant(item.id, cursorX, cursorY, next);
      cursorX += item.size.w + PARTICIPANT_GAP;
    });
    cursorY += row.height + (rowIndex < rows.length - 1 ? PARTICIPANT_GAP : 0);
  });
}

export function loadSaved() {
  try { const saved = JSON.parse(localStorage.getItem(storageKey()) || '{}') || {}; return saved.version === LAYOUT_VERSION ? saved : {}; }
  catch (_error) { return {}; }
}

function applySaved(defaults) {
  const saved = loadSaved(), savedNodes = saved.nodes || {};
  const ordered = [...state.byId.values()].sort((a, b) => depth(a.id) - depth(b.id));
  for (const node of ordered) {
    const current = state.layout.get(node.id), original = defaults.get(node.id), value = savedNodes[node.id];
    if (!current || !original) continue;
    if (value) {
      const [minW, minH] = minFor(node.type);
      state.layout.set(node.id, {
        x: Number.isFinite(value.x) ? value.x : current.x, y: Number.isFinite(value.y) ? value.y : current.y,
        w: Math.max(minW, Number(value.w) || current.w), h: Math.max(minH, Number(value.h) || current.h),
      });
      continue;
    }
    const parentId = state.parent.get(node.id), pc = state.layout.get(parentId), pd = defaults.get(parentId);
    if (pc && pd) { current.x = original.x + pc.x - pd.x; current.y = original.y + pc.y - pd.y; }
  }
  if (saved.view && Number.isFinite(saved.view.zoom)) state.view = saved.view;
  if (typeof saved.showCapabilities === 'boolean') state.showCapabilities = saved.showCapabilities;
}

export function autoLayout() {
  state.layout = new Map();
  const roots = [...state.byId.values()].filter(node => !state.parent.has(node.id));
  let x = 60, y = 60, rowH = 0;
  for (const node of roots) {
    let w, h;
    if (PARTICIPANTS.has(node.type)) { const size = measureParticipant(node.id); w = size.w; h = size.h; }
    else [w, h] = minFor(node.type);

    if (x > 60 && x + w > 1500) { x = 60; y += rowH + 80; rowH = 0; }
    if (PARTICIPANTS.has(node.type)) placeParticipant(node.id, x, y);
    else put(node.id, x, y, w, h);
    x += w + 80; rowH = Math.max(rowH, h);
  }
  const defaults = new Map([...state.layout].map(([id, value]) => [id, {...value}]));
  applySaved(defaults); normalizeContainmentGeometry();
}

export function persist() {
  const nodes = {}; state.layout.forEach((v, id) => { nodes[id] = {x: v.x, y: v.y, w: v.w, h: v.h}; });
  try { localStorage.setItem(storageKey(), JSON.stringify({version: LAYOUT_VERSION, nodes, view: state.view, showCapabilities: state.showCapabilities})); }
  catch (_error) { /* optional */ }
}

export function descendants(id, result = []) {
  for (const child of state.children.get(id) || []) { result.push(child); descendants(child, result); }
  return result;
}

function moveSubtreeLayout(id, dx, dy) {
  for (const nodeId of [id, ...descendants(id)]) {
    const box = state.layout.get(nodeId); if (!box) continue; box.x += dx; box.y += dy;
  }
}

export function constrainChildToParent(id) {
  const parentId = state.parent.get(id), child = state.layout.get(id), parent = state.layout.get(parentId);
  if (!parentId || !child || !parent) return;
  const minX = parent.x + PAD, minY = parent.y + HEADER + PAD;
  const dx = child.x < minX ? minX - child.x : 0, dy = child.y < minY ? minY - child.y : 0;
  if (dx || dy) moveSubtreeLayout(id, dx, dy);

  const corrected = state.layout.get(id);
  parent.w = Math.max(parent.w, corrected.x + corrected.w + PAD - parent.x);
  parent.h = Math.max(parent.h, corrected.y + corrected.h + PAD - parent.y);
  constrainChildToParent(parentId);
}

export function expandContainerToChildren(id) {
  const box = state.layout.get(id); if (!box || !PARTICIPANTS.has(state.byId.get(id)?.type)) return;
  const children = (state.children.get(id) || []).map(child => state.layout.get(child)).filter(Boolean); if (!children.length) return;
  const maxX = Math.max(...children.map(c => c.x + c.w)), maxY = Math.max(...children.map(c => c.y + c.h));
  const [minW, minH] = minFor(state.byId.get(id)?.type);
  box.w = Math.max(box.w, minW, maxX - box.x + PAD);
  box.h = Math.max(box.h, minH, maxY - box.y + PAD);
}

export function normalizeContainmentGeometry() {
  [...state.parent.keys()].sort((a, b) => depth(a) - depth(b)).forEach(id => constrainChildToParent(id));
  [...state.byId.values()].filter(node => PARTICIPANTS.has(node.type)).sort((a, b) => depth(b.id) - depth(a.id))
    .forEach(node => expandContainerToChildren(node.id));
}

export function expandAllContainers() { normalizeContainmentGeometry(); }

export function minimumContainerDimensions(id) {
  const [baseW, baseH] = minFor(state.byId.get(id)?.type), box = state.layout.get(id);
  const children = (state.children.get(id) || []).map(child => state.layout.get(child)).filter(Boolean);
  if (!box || !children.length) return [baseW, baseH];
  const maxX = Math.max(...children.map(c => c.x + c.w)), maxY = Math.max(...children.map(c => c.y + c.h));
  return [Math.max(baseW, maxX - box.x + PAD), Math.max(baseH, maxY - box.y + PAD)];
}