// Right-click deselection for Operational Interactions.
//
// Normal diagram behavior:
// - Left click selects an Operational Interaction and exposes its draggable
//   source/target connection anchors.
// - Right click on a selected Operational Interaction deselects only that
//   interaction, restoring its normal visual style and hiding its anchors.
// - Scenario authoring is intentionally excluded so right click cannot interfere
//   with the ordered Operational Scenario selection flow.

import {state, selectionKey} from './oa_diagram_v2_state.js';
import {updateSelection} from './oa_diagram_v2_render.js';

function deselectOperationalInteraction(event) {
  if (state.mode !== 'normal') return;

  const selectable = event.target.closest?.(
    '[data-edge-type="OPERATIONAL_EXCHANGE"][data-edge-id]'
  );
  if (!selectable) return;

  const diagramId = selectable.dataset.edgeId || '';
  if (!diagramId) return;

  const key = selectionKey('edge', diagramId);
  if (!state.selected.has(key)) return;

  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation();

  state.selected.delete(key);
  updateSelection();
}

window.addEventListener('contextmenu', deselectOperationalInteraction, {capture: true});
