(() => {
  let latestModel = {nodes: [], edges: []};
  let diagramObserver = null;
  let diagramObserverTarget = null;
  let scheduled = false;

  const clean = value => String(value ?? '').replace(/\s+/g, ' ').trim();

  function edgeId(edge, index) {
    const explicit = clean(edge?.id) || clean(edge?.key);
    if (explicit) return explicit;
    return `${edge?.type}:${edge?.source}:${edge?.target}:${clean(edge?.name)}:${index}`;
  }

  function exchangeKey(source, target, name) {
    return JSON.stringify([String(source || ''), String(target || ''), clean(name)]);
  }

  function modelMaps(model) {
    const nodes = model?.nodes || [];
    const edges = model?.edges || [];
    const byId = new Map(nodes.map(node => [node.id, node]));
    return {nodes, edges, byId};
  }

  function explicitExchangeRefs(communication) {
    if (!Array.isArray(communication?.exchange_refs)) return [];
    return communication.exchange_refs.filter(ref =>
      ref && typeof ref === 'object' && ref.source_activity_id && ref.target_activity_id
    );
  }

  function performersByActivity(model) {
    const result = new Map();
    (model?.edges || []).filter(edge => edge.type === 'PERFORMS').forEach(edge => {
      if (!result.has(edge.target)) result.set(edge.target, []);
      result.get(edge.target).push(edge.source);
    });
    return result;
  }

  function communicationMatchesParticipants(communication, first, second) {
    return (
      (communication.source === first && communication.target === second) ||
      (communication.source === second && communication.target === first)
    );
  }

  function refMatchesEdge(ref, edge) {
    if (!ref || !edge) return false;
    if (ref.source_activity_id !== edge.source || ref.target_activity_id !== edge.target) return false;
    const refName = clean(ref.exchange_name);
    return !refName || refName === clean(edge.name);
  }

  function edgeForRef(ref, edges) {
    return edges.find(edge => edge.type === 'OPERATIONAL_EXCHANGE' && refMatchesEdge(ref, edge)) || null;
  }

  function carriedExchangeRefs(communication, model) {
    const edges = model?.edges || [];
    const performers = performersByActivity(model);
    const communicationEdges = edges.filter(edge => edge.type === 'COMMUNICATION_MEAN');
    const explicit = explicitExchangeRefs(communication)
      .filter(ref => {
        const exchange = edgeForRef(ref, edges);
        return !exchange || clean(exchange.communication_assignment).toLowerCase() !== 'none';
      })
      .map(ref => ({...ref, inferred_legacy: false}));
    const result = [...explicit];

    edges.filter(edge => edge.type === 'OPERATIONAL_EXCHANGE').forEach(exchange => {
      if (result.some(ref => refMatchesEdge(ref, exchange))) return;
      if (clean(exchange.communication_assignment).toLowerCase() === 'none') return;

      const sourceParticipants = performers.get(exchange.source) || [];
      const targetParticipants = performers.get(exchange.target) || [];
      const candidateMeans = new Set();
      sourceParticipants.forEach(sourceParticipant => {
        targetParticipants.forEach(targetParticipant => {
          if (sourceParticipant === targetParticipant) return;
          communicationEdges.forEach(candidate => {
            if (communicationMatchesParticipants(candidate, sourceParticipant, targetParticipant)) {
              candidateMeans.add(edgeId(candidate, edges.indexOf(candidate)));
            }
          });
        });
      });

      const currentId = edgeId(communication, edges.indexOf(communication));
      if (candidateMeans.size !== 1 || !candidateMeans.has(currentId)) return;
      result.push({
        source_activity_id: exchange.source,
        target_activity_id: exchange.target,
        exchange_name: clean(exchange.name) || 'Interaction',
        inferred_legacy: true,
      });
    });
    return result;
  }

  function communicationAssignmentsByExchange(model) {
    const assignments = new Map();
    const communication = (model?.edges || []).filter(edge => edge.type === 'COMMUNICATION_MEAN');
    communication.forEach(edge => {
      const mediumName = clean(edge.name) || 'Communication method';
      carriedExchangeRefs(edge, model).forEach(ref => {
        const key = exchangeKey(ref.source_activity_id, ref.target_activity_id, ref.exchange_name);
        if (!assignments.has(key)) assignments.set(key, []);
        const names = assignments.get(key);
        if (!names.includes(mediumName)) names.push(mediumName);
      });
    });
    return assignments;
  }

  function matchingCommunicationSection(root) {
    return [...root.querySelectorAll('.tree-section')].find(section =>
      clean(section.querySelector(':scope > h3')?.textContent).toLowerCase() === 'communication'
    ) || null;
  }

  function exchangeLine(ref, byId) {
    const source = byId.get(ref.source_activity_id);
    const target = byId.get(ref.target_activity_id);
    const name = clean(ref.exchange_name) || 'Interaction';
    return `${name}: ${source?.name || ref.source_activity_id} → ${target?.name || ref.target_activity_id}`;
  }

  function enhanceTextualExchangeAssignments(model) {
    const root = document.getElementById('modelTextual');
    if (!root || typeof revisionTreeLine !== 'function') return;

    const edges = model?.edges || [];
    const assignments = communicationAssignmentsByExchange(model);

    root.querySelectorAll('.operational-exchange-tree-item').forEach(item => {
      const source = item.dataset.exchangeSource || '';
      const target = item.dataset.exchangeTarget || '';
      const name = item.dataset.exchangeName || '';
      const edge = edges.find(candidate =>
        candidate.type === 'OPERATIONAL_EXCHANGE' &&
        String(candidate.source || '') === source &&
        String(candidate.target || '') === target &&
        clean(candidate.name) === clean(name)
      );
      if (!edge) return;

      const children = item.querySelector(':scope > .tree-children');
      if (!children) return;
      children.querySelectorAll(':scope > .exchange-communication-line').forEach(line => line.remove());

      const names = assignments.get(exchangeKey(edge.source, edge.target, edge.name)) || [];
      const assignment = clean(edge.communication_assignment).toLowerCase();
      let text;
      if (assignment === 'none') {
        text = 'Communication: Unassigned';
      } else if (names.length) {
        text = `Communication: ${names.join(', ')}`;
      } else if (assignment === 'assigned') {
        text = 'Communication: Assigned method not available';
      } else {
        text = 'Communication: Unassigned';
      }

      children.prepend(
        revisionTreeLine(text, 'secondary exchange-communication-line')
      );
    });
  }

  function enhanceTextualCommunication(model) {
    const root = document.getElementById('modelTextual');
    if (!root || typeof revisionTreeItem !== 'function' || typeof revisionTreeLine !== 'function') return;

    const {edges, byId} = modelMaps(model);
    const communication = edges.filter(edge => edge.type === 'COMMUNICATION_MEAN');
    if (!communication.length) return;

    const section = matchingCommunicationSection(root);
    if (!section) return;

    section.querySelectorAll(':scope > .tree-item, :scope > .tree-line').forEach(node => node.remove());

    communication.forEach(edge => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      const tree = revisionTreeItem(clean(edge.name) || 'Communication method');

      tree.children.appendChild(
        revisionTreeLine(
          `${source?.name || edge.source} ↔ ${target?.name || edge.target}`,
          'secondary communication-endpoints'
        )
      );

      const refs = carriedExchangeRefs(edge, model);
      refs.forEach(ref => {
        tree.children.appendChild(
          revisionTreeLine(
            exchangeLine(ref, byId),
            `communication-carried-exchange${ref.inferred_legacy ? ' inferred-legacy' : ''}`
          )
        );
      });

      if (!refs.length) {
        tree.children.appendChild(
          revisionTreeLine('No interaction explicitly assigned to this communication method.', 'secondary communication-unassigned')
        );
      }

      section.appendChild(tree.item);
    });
  }

  function enhanceTextualPresentation(model) {
    enhanceTextualExchangeAssignments(model);
    enhanceTextualCommunication(model);
  }

  function communicationByDiagramId(model) {
    const result = new Map();
    (model?.edges || []).forEach((edge, index) => {
      if (edge.type === 'COMMUNICATION_MEAN') result.set(edgeId(edge, index), edge);
    });
    return result;
  }

  function appendSvgLine(label, text, className, dy) {
    const tspan = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
    tspan.setAttribute('x', label.getAttribute('x') || '0');
    tspan.setAttribute('dy', String(dy));
    tspan.setAttribute('class', className);
    tspan.textContent = text;
    label.appendChild(tspan);
  }

  function enhanceDiagramCommunicationLabels() {
    scheduled = false;
    const root = document.getElementById('oaDiagramEdges');
    if (!root) return;

    const {byId} = modelMaps(latestModel);
    const communication = communicationByDiagramId(latestModel);

    root.querySelectorAll('.communication-label[data-edge-id]').forEach(label => {
      const edge = communication.get(clean(label.dataset.edgeId));
      if (!edge) return;

      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      const refs = carriedExchangeRefs(edge, latestModel);
      const signature = JSON.stringify([
        clean(edge.name), edge.source, edge.target,
        refs.map(ref => [ref.source_activity_id, ref.target_activity_id, clean(ref.exchange_name), !!ref.inferred_legacy])
      ]);
      if (label.dataset.communicationPresentation === signature) return;

      label.textContent = '';
      label.dataset.communicationPresentation = signature;
      appendSvgLine(label, clean(edge.name) || 'Communication mean', 'communication-name-line', 0);
      appendSvgLine(
        label,
        `${source?.name || edge.source} ↔ ${target?.name || edge.target}`,
        'communication-endpoints-line',
        13
      );

      refs.slice(0, 3).forEach(ref => {
        appendSvgLine(
          label,
          `↳ ${clean(ref.exchange_name) || 'Interaction'}`,
          `communication-exchange-line${ref.inferred_legacy ? ' inferred-legacy' : ''}`,
          12
        );
      });
      if (refs.length > 3) {
        appendSvgLine(label, `↳ +${refs.length - 3} more`, 'communication-exchange-line', 12);
      }

      label.setAttribute(
        'aria-label',
        `${clean(edge.name) || 'Communication mean'} between ${source?.name || edge.source} and ${target?.name || edge.target}`
      );
    });
  }

  function scheduleDiagramEnhancement() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(enhanceDiagramCommunicationLabels);
  }

  function ensureDiagramObserver() {
    const root = document.getElementById('oaDiagramEdges');
    if (!root || root === diagramObserverTarget) return;
    diagramObserver?.disconnect();
    diagramObserverTarget = root;
    diagramObserver = new MutationObserver(scheduleDiagramEnhancement);
    diagramObserver.observe(root, {childList: true, subtree: true});
    scheduleDiagramEnhancement();
  }

  window.addEventListener('oa:diagram-model-rendered', event => {
    latestModel = event?.detail?.model || {nodes: [], edges: []};
    ensureDiagramObserver();
    scheduleDiagramEnhancement();
  });

  window.addEventListener('mbse:model-projections-updated', event => {
    latestModel = event?.detail?.model || {nodes: [], edges: []};
    // Pseudo-code has already been regenerated by the generic projection sync.
    // Apply communication-specific hierarchy/assignment decoration afterwards.
    enhanceTextualPresentation(latestModel);
    ensureDiagramObserver();
    scheduleDiagramEnhancement();
  });

  const bodyObserver = new MutationObserver(() => ensureDiagramObserver());
  bodyObserver.observe(document.body, {childList: true, subtree: true});

  if (typeof applyState === 'function') {
    const baseApplyState = applyState;
    applyState = function communicationAwareApplyState(state) {
      latestModel = state?.model || {nodes: [], edges: []};
      baseApplyState(state);
      // Fallback for older pages where the generic synchronizer is unavailable.
      if (!window.mbseModelProjectionSync) enhanceTextualPresentation(latestModel);
      ensureDiagramObserver();
      scheduleDiagramEnhancement();
    };
  }

  const synchronized = window.mbseModelProjectionSync?.getLatest?.();
  if (synchronized?.signature) {
    latestModel = synchronized.model || latestModel;
    enhanceTextualPresentation(latestModel);
  }
  ensureDiagramObserver();
})();