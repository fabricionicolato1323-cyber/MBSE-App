// Operational Interaction overlap routing.
//
// Visual requirement:
// - Two Operational Interactions must never remain 100% superimposed outside a
//   Communication Mean.
// - Interactions may cross and may share short portions/endpoints.
// - The Communication Mean itself may be shared by several interactions.
//
// The diagram renderer already emits cubic Bezier paths for direct exchanges and
// for the Activity <-> Communication Mean access segments. This presentation
// layer detects paths with the same pair of endpoints and fans their control
// points into parallel visual lanes while preserving the exact semantic start
// and end anchors. No model data is changed.

(() => {
  if (window.__oaInteractionOverlapRoutingInstalled) return;
  window.__oaInteractionOverlapRoutingInstalled = true;

  const ROUTE_GAP = 20;
  const EPSILON = 0.5;
  let scheduled = false;
  let observer = null;

  function numbersFromPath(pathData) {
    const values = String(pathData || '').match(/-?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?/gi);
    if (!values || values.length < 8) return null;
    const numbers = values.slice(0, 8).map(Number);
    return numbers.every(Number.isFinite) ? numbers : null;
  }

  function pointKey(point) {
    const x = Math.round(point.x / EPSILON) * EPSILON;
    const y = Math.round(point.y / EPSILON) * EPSILON;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }

  function canonicalGeometry(values) {
    const start = {x: values[0], y: values[1]};
    const end = {x: values[6], y: values[7]};
    const startKey = pointKey(start);
    const endKey = pointKey(end);
    const forward = startKey <= endKey;
    const a = forward ? start : end;
    const b = forward ? end : start;
    return {
      key: forward ? `${startKey}|${endKey}` : `${endKey}|${startKey}`,
      a,
      b,
    };
  }

  function canonicalNormal(geometry) {
    const dx = geometry.b.x - geometry.a.x;
    const dy = geometry.b.y - geometry.a.y;
    const length = Math.hypot(dx, dy) || 1;
    return {x: -dy / length, y: dx / length};
  }

  function basePathData(path) {
    if (!path.dataset.oaOverlapBaseD) {
      path.dataset.oaOverlapBaseD = path.getAttribute('d') || '';
    }
    return path.dataset.oaOverlapBaseD;
  }

  function baseLabelPosition(label) {
    if (!label.dataset.oaOverlapBaseX) {
      label.dataset.oaOverlapBaseX = label.getAttribute('x') || '0';
      label.dataset.oaOverlapBaseY = label.getAttribute('y') || '0';
    }
    return {
      x: Number(label.dataset.oaOverlapBaseX) || 0,
      y: Number(label.dataset.oaOverlapBaseY) || 0,
    };
  }

  function pathForLane(values, normal, offset) {
    const c1x = values[2] + normal.x * offset;
    const c1y = values[3] + normal.y * offset;
    const c2x = values[4] + normal.x * offset;
    const c2y = values[5] + normal.y * offset;
    return `M ${values[0]} ${values[1]} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${values[6]} ${values[7]}`;
  }

  function labelForPath(path, edgeRoot) {
    if (!(path.classList.contains('direct-exchange') || path.classList.contains('source-segment'))) {
      return null;
    }
    const edgeId = path.dataset.edgeId || '';
    if (!edgeId) return null;
    const escaped = CSS.escape(edgeId);
    return edgeRoot.querySelector(`.oa-diagram-edge-label.interaction-label[data-edge-id="${escaped}"]`);
  }

  function laneSortKey(path) {
    const id = path.dataset.edgeId || '';
    const classHint = path.classList.contains('source-segment')
      ? 'source'
      : path.classList.contains('target-segment')
        ? 'target'
        : 'direct';
    return `${id}|${classHint}`;
  }

  function separateOverlaps() {
    scheduled = false;
    const edgeRoot = document.getElementById('oaDiagramEdges');
    if (!edgeRoot) return;

    const paths = [...edgeRoot.querySelectorAll('path.oa-diagram-edge.operational-exchange')];
    const groups = new Map();

    paths.forEach(path => {
      const baseD = basePathData(path);
      const values = numbersFromPath(baseD);
      if (!values) return;
      const geometry = canonicalGeometry(values);
      if (!groups.has(geometry.key)) groups.set(geometry.key, []);
      groups.get(geometry.key).push({path, values, geometry});
    });

    groups.forEach(items => {
      items.sort((left, right) => laneSortKey(left.path).localeCompare(laneSortKey(right.path)));

      // A single route does not need a lane offset. Restore its original geometry
      // in case a previous render temporarily had a parallel neighbour.
      if (items.length === 1) {
        const {path} = items[0];
        path.setAttribute('d', basePathData(path));
        const label = labelForPath(path, edgeRoot);
        if (label) {
          const base = baseLabelPosition(label);
          label.setAttribute('x', String(base.x));
          label.setAttribute('y', String(base.y));
        }
        return;
      }

      const normal = canonicalNormal(items[0].geometry);
      items.forEach((item, index) => {
        const lane = index - (items.length - 1) / 2;
        const offset = lane * ROUTE_GAP;
        item.path.setAttribute('d', pathForLane(item.values, normal, offset));
        item.path.dataset.oaOverlapLane = String(lane);

        const label = labelForPath(item.path, edgeRoot);
        if (label) {
          const base = baseLabelPosition(label);
          label.setAttribute('x', String(base.x + normal.x * offset));
          label.setAttribute('y', String(base.y + normal.y * offset));
          label.dataset.oaOverlapLane = String(lane);
        }
      });
    });
  }

  function scheduleSeparation() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(separateOverlaps);
  }

  function installObserver() {
    const edgeRoot = document.getElementById('oaDiagramEdges');
    if (!edgeRoot) {
      requestAnimationFrame(installObserver);
      return;
    }
    observer?.disconnect();
    observer = new MutationObserver(scheduleSeparation);
    observer.observe(edgeRoot, {childList: true, subtree: true});
    scheduleSeparation();
  }

  window.addEventListener('oa:diagram-model-rendered', scheduleSeparation);
  window.addEventListener('pointerup', scheduleSeparation, {capture: true});
  window.addEventListener('resize', scheduleSeparation);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installObserver, {once: true});
  } else {
    installObserver();
  }
})();
