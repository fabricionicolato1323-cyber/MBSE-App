export const PARTICIPANTS = new Set(['OperationalEntity', 'OperationalActor']);
export const MIN = {
  OperationalEntity: [300, 190], OperationalActor: [260, 175],
  OperationalActivity: [190, 72], OperationalCapability: [210, 76], Pending: [180, 68],
};
export const PAD = 22, HEADER = 54, GAP = 18, LAYOUT_VERSION = 2;

export const state = {
  session: 'default', model: {nodes: [], drafts: [], edges: []},
  byId: new Map(), parent: new Map(), children: new Map(), performersByActivity: new Map(),
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
export const edgeId = (edge, i) => clean(edge.id) || `${edge.type}:${edge.source}:${edge.target}:${clean(edge.name)}:${i}`;
export const storageKey = () => `oa-diagram-layout:v${LAYOUT_VERSION}:${state.session}`;

export function validContainment(parent, child) {
  if (!parent || !child) return false;
  if (parent.type === 'OperationalEntity') return PARTICIPANTS.has(child.type);
  if (parent.type === 'OperationalActor') return child.type === 'OperationalActor';
  return false;
}

export const isVisibleNode = node => !!node && (state.showCapabilities || node.type !== 'OperationalCapability');
export const visibleLayoutEntries = () => [...state.layout.entries()].filter(([id]) => isVisibleNode(state.byId.get(id)));

export function buildModel(model) {
  const nodes = [...(model.nodes || []), ...(model.drafts || [])], edges = model.edges || [];
  state.byId = new Map(nodes.map(node => [node.id, node]));
  state.parent = new Map(); state.children = new Map(); state.performersByActivity = new Map();
  state.communicationMeans = []; state.invalidContainments = [];
  const addParent = (child, parent) => {
    if (!child || !parent || child === parent || state.parent.has(child)) return;
    state.parent.set(child, parent);
    if (!state.children.has(parent)) state.children.set(parent, []);
    state.children.get(parent).push(child);
  };
  edges.filter(edge => edge.type === 'CONTAINS').forEach(edge => {
    const parent = state.byId.get(edge.source), child = state.byId.get(edge.target);
    if (!PARTICIPANTS.has(parent?.type) || !PARTICIPANTS.has(child?.type)) return;
    if (!validContainment(parent, child)) { state.invalidContainments.push(edge); return; }
    addParent(child.id, parent.id);
  });
  edges.filter(edge => edge.type === 'PERFORMS').forEach(edge => {
    const performer = state.byId.get(edge.source), activity = state.byId.get(edge.target);
    if (!PARTICIPANTS.has(performer?.type) || activity?.type !== 'OperationalActivity') return;
    if (!state.performersByActivity.has(activity.id)) state.performersByActivity.set(activity.id, []);
    state.performersByActivity.get(activity.id).push(performer.id);
    addParent(activity.id, performer.id);
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
  const sizes = participants.map(child => measureParticipant(child.id, next));
  const participantW = sizes.reduce((sum, size) => sum + size.w, 0) + Math.max(0, sizes.length - 1) * GAP;
  const participantH = sizes.reduce((max, size) => Math.max(max, size.h), 0);
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
  const next = new Set(seen); next.add(id); const size = measureParticipant(id, next); put(id, x, y, size.w, size.h);
  const activities = childNodes(id, child => child.type === 'OperationalActivity');
  const participants = childNodes(id, child => PARTICIPANTS.has(child.type));
  let cursorY = y + HEADER + PAD;
  for (const activity of activities) {
    const [w, h] = minFor(activity.type); put(activity.id, x + PAD, cursorY, Math.min(w, size.w - PAD * 2), h); cursorY += h + GAP;
  }
  if (activities.length && participants.length) cursorY += GAP;
  let cursorX = x + PAD;
  for (const participant of participants) {
    const childSize = measureParticipant(participant.id, next); placeParticipant(participant.id, cursorX, cursorY, next); cursorX += childSize.w + GAP;
  }
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
      state.layout.set(node.id, {x: Number.isFinite(value.x) ? value.x : current.x, y: Number.isFinite(value.y) ? value.y : current.y,
        w: Math.max(minW, Number(value.w) || current.w), h: Math.max(minH, Number(value.h) || current.h)});
      continue;
    }
    const parentId = state.parent.get(node.id), pc = state.layout.get(parentId), pd = defaults.get(parentId);
    if (pc && pd) { current.x = original.x + pc.x - pd.x; current.y = original.y + pc.y - pd.y; }
  }
  if (saved.view && Number.isFinite(saved.view.zoom)) state.view = saved.view;
  if (typeof saved.showCapabilities === 'boolean') state.showCapabilities = saved.showCapabilities;
}

export function autoLayout() {
  state.layout = new Map(); const roots = [...state.byId.values()].filter(node => !state.parent.has(node.id));
  let x = 60, y = 60, rowH = 0;
  for (const node of roots) {
    let w, h;
    if (PARTICIPANTS.has(node.type)) { const size = measureParticipant(node.id); w = size.w; h = size.h; placeParticipant(node.id, x, y); }
    else { [w, h] = minFor(node.type); put(node.id, x, y, w, h); }
    if (x + w > 1500) { x = 60; y += rowH + 80; rowH = 0; }
    else { x += w + 80; rowH = Math.max(rowH, h); }
  }
  const defaults = new Map([...state.layout].map(([id, value]) => [id, {...value}])); applySaved(defaults); expandAllContainers();
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

export function expandContainerToChildren(id) {
  const box = state.layout.get(id); if (!box || !PARTICIPANTS.has(state.byId.get(id)?.type)) return;
  const children = (state.children.get(id) || []).map(child => state.layout.get(child)).filter(Boolean); if (!children.length) return;
  const minX = Math.min(...children.map(c => c.x)), minY = Math.min(...children.map(c => c.y));
  const maxX = Math.max(...children.map(c => c.x + c.w)), maxY = Math.max(...children.map(c => c.y + c.h));
  const x = Math.min(box.x, minX - PAD), y = Math.min(box.y, minY - HEADER - PAD);
  const right = Math.max(box.x + box.w, maxX + PAD), bottom = Math.max(box.y + box.h, maxY + PAD);
  const [minW, minH] = minFor(state.byId.get(id)?.type);
  Object.assign(box, {x, y, w: Math.max(minW, right - x), h: Math.max(minH, bottom - y)});
}

export function expandAllContainers() {
  [...state.byId.values()].filter(node => PARTICIPANTS.has(node.type)).sort((a, b) => depth(b.id) - depth(a.id))
    .forEach(node => expandContainerToChildren(node.id));
}

export function minimumContainerDimensions(id) {
  const [baseW, baseH] = minFor(state.byId.get(id)?.type), box = state.layout.get(id);
  const children = (state.children.get(id) || []).map(child => state.layout.get(child)).filter(Boolean);
  if (!box || !children.length) return [baseW, baseH];
  const maxX = Math.max(...children.map(c => c.x + c.w)), maxY = Math.max(...children.map(c => c.y + c.h));
  return [Math.max(baseW, maxX - box.x + PAD), Math.max(baseH, maxY - box.y + PAD)];
}
