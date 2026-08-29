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

      const refs = explicitExchangeRefs(edge);
      refs.forEach(ref => {
        tree.children.appendChild(
          revisionTreeLine(exchangeLine(ref, byId), 'communication-carried-exchange')
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
      const refs = explicitExchangeRefs(edge);
      const signature = JSON.stringify([
        clean(edge.name), edge.source, edge.target,
        refs.map(ref => [ref.source_activity_id, ref.target_activity_id, clean(ref.exchange_name)])
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
          'communication-exchange-line',
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

  const bodyObserver = new MutationObserver(() => ensureDiagramObserver());
  bodyObserver.observe(document.body, {childList: true, subtree: true});

  if (typeof applyState === 'function') {
    const baseApplyState = applyState;
    applyState = function communicationAwareApplyState(state) {
      latestModel = state?.model || {nodes: [], edges: []};
      baseApplyState(state);
      enhanceTextualCommunication(latestModel);
      ensureDiagramObserver();
      scheduleDiagramEnhancement();
    };
  }

  ensureDiagramObserver();
})();
