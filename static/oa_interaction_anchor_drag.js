// Draggable Operational Interaction connection anchors.
//
// Visual requirement:
// - Every Operational Interaction endpoint attached to an Operational Activity
//   can be repositioned along that Activity boundary.
// - Source and target endpoints are independent, so outgoing and incoming
//   connections can be visually separated.
// - This is presentation-only. The semantic source/target of the exchange never
//   changes.
// - Anchor positions are persisted per live diagram session.

import {state, edgeId} from './oa_diagram_v2_state.js';
import {getCanvasOrigin} from './oa_diagram_v2_render.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const ANCHOR_LAYOUT_VERSION = 1;
const MIN_RATIO = 0.04;
const MAX_RATIO = 0.96;

let loadedSession = null;
let placements = {};
let drag = null;
let observer = null;
let scheduled = false;
let resetButton = null;

const clean = value => String(value ?? '').replace(/\s+/g, ' ').trim();

function storageKey() {
  return `oa-interaction-anchors:v${ANCHOR_LAYOUT_VERSION}:${state.session || 'default'}`;
}

function ensurePlacementsLoaded() {
  const session = state.session || 'default';
  if (loadedSession === session) return;
  loadedSession = session;
  placements = {};
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey()) || '{}') || {};
    if (saved && typeof saved === 'object') placements = saved;
  } catch (_error) {
    placements = {};
  }
}

function persistPlacements() {
  ensurePlacementsLoaded();
  try {
    localStorage.setItem(storageKey(), JSON.stringify(placements));
  } catch (_error) {
    // Presentation persistence is optional.
  }
}

function placementFor(edgeDiagramId, role) {
  ensurePlacementsLoaded();
  return placements?.[edgeDiagramId]?.[role] || null;
}

function setPlacement(edgeDiagramId, role, placement) {
  ensurePlacementsLoaded();
  if (!placements[edgeDiagramId]) placements[edgeDiagramId] = {};
  placements[edgeDiagramId][role] = placement;
}

function exchangeRecordByDiagramId(diagramId) {
  const edges = Array.isArray(state.model?.edges) ? state.model.edges : [];
  for (let index = 0; index < edges.length; index += 1) {
    const edge = edges[index];
    if (edge?.type !== 'OPERATIONAL_EXCHANGE') continue;
    if (edgeId(edge, index) === diagramId) return {edge, index};
  }
  return null;
}

function numbersFromPath(pathData) {
  const values = String(pathData || '').match(/-?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?/gi);
  if (!values || values.length < 8) return null;
  const numbers = values.slice(0, 8).map(Number);
  return numbers.every(Number.isFinite) ? numbers : null;
}

function rendererBasePath(path) {
  if (!path.dataset.oaAnchorRendererBaseD) {
    path.dataset.oaAnchorRendererBaseD = path.dataset.oaOverlapBaseD || path.getAttribute('d') || '';
  }
  return path.dataset.oaAnchorRendererBaseD;
}

function boxForActivity(activityId) {
  const node = state.byId.get(activityId);
  const box = state.layout.get(activityId);
  if (node?.type !== 'OperationalActivity' || !box) return null;
  return box;
}

function pointForPlacement(activityId, placement) {
  const box = boxForActivity(activityId);
  if (!box || !placement) return null;
  const ratio = Math.max(MIN_RATIO, Math.min(MAX_RATIO, Number(placement.ratio) || 0.5));
  switch (placement.side) {
    case 'left':
      return {x: box.x, y: box.y + box.h * ratio, side: 'left'};
    case 'right':
      return {x: box.x + box.w, y: box.y + box.h * ratio, side: 'right'};
    case 'top':
      return {x: box.x + box.w * ratio, y: box.y, side: 'top'};
    case 'bottom':
      return {x: box.x + box.w * ratio, y: box.y + box.h, side: 'bottom'};
    default:
      return null;
  }
}

function sideForBoundaryPoint(activityId, point) {
  const box = boxForActivity(activityId);
  if (!box || !point) return null;
  const distances = [
    ['left', Math.abs(point.x - box.x)],
    ['right', Math.abs(point.x - (box.x + box.w))],
    ['top', Math.abs(point.y - box.y)],
    ['bottom', Math.abs(point.y - (box.y + box.h))],
  ];
  distances.sort((a, b) => a[1] - b[1]);
  return distances[0][0];
}

function outwardNormal(side) {
  switch (side) {
    case 'left': return {x: -1, y: 0};
    case 'right': return {x: 1, y: 0};
    case 'top': return {x: 0, y: -1};
    case 'bottom': return {x: 0, y: 1};
    default: return null;
  }
}

function curveWithAnchors(start, end, startSide = null, endSide = null) {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = Math.hypot(dx, dy) || 1;
  const ux = dx / length;
  const uy = dy / length;
  const reach = Math.max(42, Math.min(150, length * 0.34));
  const startNormal = outwardNormal(startSide);
  const endNormal = outwardNormal(endSide);

  const c1 = startNormal
    ? {x: start.x + startNormal.x * reach, y: start.y + startNormal.y * reach}
    : {x: start.x + ux * reach, y: start.y + uy * reach};
  const c2 = endNormal
    ? {x: end.x + endNormal.x * reach, y: end.y + endNormal.y * reach}
    : {x: end.x - ux * reach, y: end.y - uy * reach};

  return `M ${start.x} ${start.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${end.x} ${end.y}`;
}

function setPathBase(path, data) {
  if (!path || !data) return;
  path.setAttribute('d', data);
  // The overlap-routing layer fans control points from this canonical baseline.
  path.dataset.oaOverlapBaseD = data;
}

function interactionLabel(edgeRoot, diagramId) {
  if (!edgeRoot || !diagramId) return null;
  return edgeRoot.querySelector(
    `.oa-diagram-edge-label.interaction-label[data-edge-id="${CSS.escape(diagramId)}"]`
  );
}

function setLabelBase(label, x, y) {
  if (!label) return;
  label.setAttribute('x', String(x));
  label.setAttribute('y', String(y));
  label.dataset.oaOverlapBaseX = String(x);
  label.dataset.oaOverlapBaseY = String(y);
}

function applyAnchorsToExchange(diagramId, record = exchangeRecordByDiagramId(diagramId)) {
  if (!record) return false;
  const edgeRoot = document.getElementById('oaDiagramEdges');
  if (!edgeRoot) return false;
  const {edge} = record;
  const sourcePlacement = placementFor(diagramId, 'source');
  const targetPlacement = placementFor(diagramId, 'target');
  if (!sourcePlacement && !targetPlacement) return false;

  const escaped = CSS.escape(diagramId);
  const direct = edgeRoot.querySelector(
    `path.oa-diagram-edge.operational-exchange.direct-exchange[data-edge-id="${escaped}"]`
  );
  const sourceSegment = edgeRoot.querySelector(
    `path.oa-diagram-edge.operational-exchange.source-segment[data-edge-id="${escaped}"]`
  );
  const targetSegment = edgeRoot.querySelector(
    `path.oa-diagram-edge.operational-exchange.target-segment[data-edge-id="${escaped}"]`
  );

  let changed = false;

  if (direct) {
    const values = numbersFromPath(rendererBasePath(direct));
    if (values) {
      const defaultSource = {x: values[0], y: values[1]};
      const defaultTarget = {x: values[6], y: values[7]};
      const source = pointForPlacement(edge.source, sourcePlacement) || {
        ...defaultSource,
        side: sideForBoundaryPoint(edge.source, defaultSource),
      };
      const target = pointForPlacement(edge.target, targetPlacement) || {
        ...defaultTarget,
        side: sideForBoundaryPoint(edge.target, defaultTarget),
      };
      setPathBase(direct, curveWithAnchors(source, target, source.side, target.side));
      setLabelBase(interactionLabel(edgeRoot, diagramId), (source.x + target.x) / 2, (source.y + target.y) / 2 - 8);
      changed = true;
    }
  } else {
    if (sourceSegment && sourcePlacement) {
      const values = numbersFromPath(rendererBasePath(sourceSegment));
      const source = pointForPlacement(edge.source, sourcePlacement);
      if (values && source) {
        const fixedEnd = {x: values[6], y: values[7]};
        setPathBase(sourceSegment, curveWithAnchors(source, fixedEnd, source.side, null));
        setLabelBase(interactionLabel(edgeRoot, diagramId), (source.x + fixedEnd.x) / 2, (source.y + fixedEnd.y) / 2 - 8);
        changed = true;
      }
    }
    if (targetSegment && targetPlacement) {
      const values = numbersFromPath(rendererBasePath(targetSegment));
      const target = pointForPlacement(edge.target, targetPlacement);
      if (values && target) {
        const fixedStart = {x: values[0], y: values[1]};
        setPathBase(targetSegment, curveWithAnchors(fixedStart, target, null, target.side));
        changed = true;
      }
    }
  }

  return changed;
}

function endpointForRole(diagramId, role) {
  const edgeRoot = document.getElementById('oaDiagramEdges');
  if (!edgeRoot) return null;
  const escaped = CSS.escape(diagramId);
  const direct = edgeRoot.querySelector(
    `path.oa-diagram-edge.operational-exchange.direct-exchange[data-edge-id="${escaped}"]`
  );
  if (direct) {
    const values = numbersFromPath(direct.dataset.oaOverlapBaseD || direct.getAttribute('d'));
    if (!values) return null;
    return role === 'source'
      ? {x: values[0], y: values[1]}
      : {x: values[6], y: values[7]};
  }

  const selector = role === 'source'
    ? `path.oa-diagram-edge.operational-exchange.source-segment[data-edge-id="${escaped}"]`
    : `path.oa-diagram-edge.operational-exchange.target-segment[data-edge-id="${escaped}"]`;
  const path = edgeRoot.querySelector(selector);
  const values = path ? numbersFromPath(path.dataset.oaOverlapBaseD || path.getAttribute('d')) : null;
  if (!values) return null;
  return role === 'source'
    ? {x: values[0], y: values[1]}
    : {x: values[6], y: values[7]};
}

function selectedExchangeIds() {
  if (state.mode !== 'normal') return [];
  const result = [];
  for (const key of state.selected) {
    if (!key.startsWith('edge:')) continue;
    const id = key.slice(5);
    if (exchangeRecordByDiagramId(id)) result.push(id);
  }
  return result;
}

function makeHandle(diagramId, role, activityId, point) {
  const handle = document.createElementNS(SVG_NS, 'circle');
  handle.classList.add('oa-interaction-anchor-handle', `oa-interaction-anchor-${role}`);
  handle.dataset.edgeId = diagramId;
  handle.dataset.anchorRole = role;
  handle.dataset.activityId = activityId;
  handle.setAttribute('cx', String(point.x));
  handle.setAttribute('cy', String(point.y));
  handle.setAttribute('r', role === 'source' ? '6.5' : '6');
  handle.setAttribute('tabindex', '0');
  handle.setAttribute('role', 'button');
  handle.setAttribute('aria-label', role === 'source'
    ? 'Move Operational Interaction source connection point'
    : 'Move Operational Interaction target connection point');
  const title = document.createElementNS(SVG_NS, 'title');
  title.textContent = role === 'source'
    ? 'Drag to move the outgoing connection point around the Activity boundary'
    : 'Drag to move the incoming connection point around the Activity boundary';
  handle.appendChild(title);
  return handle;
}

function refreshHandles() {
  const edgeRoot = document.getElementById('oaDiagramEdges');
  if (!edgeRoot) return;
  edgeRoot.querySelectorAll('.oa-interaction-anchor-handle').forEach(node => node.remove());
  if (state.mode !== 'normal') return;

  selectedExchangeIds().forEach(diagramId => {
    const record = exchangeRecordByDiagramId(diagramId);
    if (!record) return;
    const sourcePoint = endpointForRole(diagramId, 'source');
    const targetPoint = endpointForRole(diagramId, 'target');
    if (sourcePoint) edgeRoot.appendChild(makeHandle(diagramId, 'source', record.edge.source, sourcePoint));
    if (targetPoint) edgeRoot.appendChild(makeHandle(diagramId, 'target', record.edge.target, targetPoint));
  });
}

function applyAllSavedAnchors() {
  ensurePlacementsLoaded();
  let changed = false;
  Object.keys(placements).forEach(diagramId => {
    changed = applyAnchorsToExchange(diagramId) || changed;
  });
  if (changed) window.dispatchEvent(new CustomEvent('oa:interaction-anchors-updated'));
  refreshHandles();
}

function scheduleApply() {
  if (scheduled) return;
  scheduled = true;
  requestAnimationFrame(() => {
    scheduled = false;
    applyAllSavedAnchors();
  });
}

function pointerToModel(event) {
  const viewport = document.getElementById('oaDiagramViewport');
  if (!viewport) return null;
  const rect = viewport.getBoundingClientRect();
  const origin = getCanvasOrigin();
  const zoom = Math.max(0.0001, Number(state.view.zoom) || 1);
  const contentX = event.clientX - rect.left + viewport.scrollLeft;
  const contentY = event.clientY - rect.top + viewport.scrollTop;
  return {
    x: (contentX - (Number(state.view.x) || 0)) / zoom - origin.x,
    y: (contentY - (Number(state.view.y) || 0)) / zoom - origin.y,
  };
}

function placementFromPointer(activityId, event) {
  const box = boxForActivity(activityId);
  const point = pointerToModel(event);
  if (!box || !point) return null;

  const candidates = [
    {side: 'left', distance: Math.abs(point.x - box.x)},
    {side: 'right', distance: Math.abs(point.x - (box.x + box.w))},
    {side: 'top', distance: Math.abs(point.y - box.y)},
    {side: 'bottom', distance: Math.abs(point.y - (box.y + box.h))},
  ].sort((a, b) => a.distance - b.distance);

  const side = candidates[0].side;
  let ratio;
  if (side === 'left' || side === 'right') {
    ratio = (point.y - box.y) / Math.max(1, box.h);
  } else {
    ratio = (point.x - box.x) / Math.max(1, box.w);
  }
  return {side, ratio: Math.max(MIN_RATIO, Math.min(MAX_RATIO, ratio))};
}

function updateStatus(message) {
  const status = document.getElementById('oaDiagramStatus');
  if (status) status.textContent = message;
}

function beginDrag(event) {
  const handle = event.target.closest?.('.oa-interaction-anchor-handle');
  if (!handle || event.button !== 0 || state.mode !== 'normal') return;
  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation();
  drag = {
    pointerId: event.pointerId,
    diagramId: handle.dataset.edgeId || '',
    role: handle.dataset.anchorRole || '',
    activityId: handle.dataset.activityId || '',
  };
  document.body.classList.add('oa-interaction-anchor-dragging');
  updateStatus(`Move the ${drag.role === 'source' ? 'outgoing' : 'incoming'} connection point around the Operational Activity boundary.`);
}

function moveDrag(event) {
  if (!drag || event.pointerId !== drag.pointerId) return;
  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation();
  const placement = placementFromPointer(drag.activityId, event);
  if (!placement) return;
  setPlacement(drag.diagramId, drag.role, placement);
  const changed = applyAnchorsToExchange(drag.diagramId);
  if (changed) {
    window.dispatchEvent(new CustomEvent('oa:interaction-anchors-updated'));
    refreshHandles();
  }
}

function endDrag(event) {
  if (!drag || (event.pointerId != null && event.pointerId !== drag.pointerId)) return;
  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation();
  persistPlacements();
  state.suppressClickUntil = Date.now() + 180;
  drag = null;
  document.body.classList.remove('oa-interaction-anchor-dragging');
  updateStatus('Connection point saved. Select an Operational Interaction to move its source or target connection point again.');
  scheduleApply();
}

function ensureStyles() {
  if (document.getElementById('oaInteractionAnchorStyle')) return;
  const style = document.createElement('style');
  style.id = 'oaInteractionAnchorStyle';
  style.textContent = `
    .oa-interaction-anchor-handle {
      pointer-events: all;
      vector-effect: non-scaling-stroke;
      stroke: #174a8b;
      stroke-width: 2px;
      cursor: move;
      filter: drop-shadow(0 1px 1px rgba(0,0,0,.18));
    }
    .oa-interaction-anchor-source {
      fill: #fcfcfa;
    }
    .oa-interaction-anchor-target {
      fill: #174a8b;
    }
    .oa-interaction-anchor-handle:hover,
    .oa-interaction-anchor-handle:focus-visible {
      stroke-width: 3px;
      outline: none;
      filter: drop-shadow(0 0 3px rgba(23,74,139,.45));
    }
    #diagramTab.oa-scenario-authoring-active .oa-interaction-anchor-handle {
      display: none !important;
    }
    body.oa-interaction-anchor-dragging {
      user-select: none;
      cursor: move !important;
    }
  `;
  document.head.appendChild(style);
}

function bindReset() {
  const reset = document.getElementById('oaDiagramReset');
  if (!reset || reset === resetButton) return;
  resetButton = reset;
  reset.addEventListener('click', () => {
    ensurePlacementsLoaded();
    try { localStorage.removeItem(storageKey()); } catch (_error) {}
    placements = {};
    scheduleApply();
  });
}

function installObserver() {
  const edgeRoot = document.getElementById('oaDiagramEdges');
  if (!edgeRoot) {
    requestAnimationFrame(installObserver);
    return;
  }
  observer?.disconnect();
  observer = new MutationObserver(mutations => {
    const relevant = mutations.some(mutation =>
      [...mutation.addedNodes, ...mutation.removedNodes].some(node =>
        !(node.nodeType === 1 && node.classList?.contains('oa-interaction-anchor-handle'))
      )
    );
    if (relevant) scheduleApply();
  });
  observer.observe(edgeRoot, {childList: true, subtree: true});
  bindReset();
  scheduleApply();
}

ensureStyles();
window.addEventListener('pointerdown', beginDrag, {capture: true});
window.addEventListener('pointermove', moveDrag, {capture: true});
window.addEventListener('pointerup', endDrag, {capture: true});
window.addEventListener('pointercancel', endDrag, {capture: true});
window.addEventListener('oa:diagram-selection-change', scheduleApply);
window.addEventListener('oa:diagram-model-rendered', () => {
  ensurePlacementsLoaded();
  bindReset();
  scheduleApply();
});
window.addEventListener('resize', scheduleApply);

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', installObserver, {once: true});
} else {
  installObserver();
}
