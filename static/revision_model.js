function revisionFriendlyType(type) {
  return ({
    OperationalCapability: 'Goal',
    OperationalActor: 'Person / role',
    OperationalEntity: 'Participant / context',
    OperationalActivity: 'Action',
    Pending: 'Temporary input'
  })[type] || type || 'Item';
}

function revisionFriendlyRelation(type) {
  return ({
    PERFORMS: 'performs',
    SUPPORTS_CAPABILITY: 'supports',
    OPERATIONAL_EXCHANGE: 'exchange',
    COMMUNICATION_MEAN: 'communication',
    CONTAINS: 'contains',
    LOCATED_IN: 'located in',
    DECOMPOSES: 'breaks down into'
  })[type] || String(type || '').toLowerCase().replaceAll('_', ' ');
}

function revisionTreeLine(text, className = '') {
  const line = document.createElement('div');
  line.className = `tree-line ${className}`.trim();
  line.textContent = text;
  return line;
}

function revisionTreeItem(title, meta = '', temporary = false) {
  const item = document.createElement('div');
  item.className = `tree-item${temporary ? ' temporary' : ''}`;
  const header = document.createElement('div');
  header.className = 'tree-item-header';
  const name = document.createElement('span');
  name.className = 'tree-item-name';
  name.textContent = title;
  header.appendChild(name);
  if (meta) {
    const badge = document.createElement('span');
    badge.className = 'tree-item-meta';
    badge.textContent = meta;
    header.appendChild(badge);
  }
  item.appendChild(header);
  const children = document.createElement('div');
  children.className = 'tree-children';
  item.appendChild(children);
  return {item, children};
}

function revisionAppendCharacteristics(container, node) {
  if (!Array.isArray(node.characteristics)) return;
  node.characteristics.forEach(characteristic => {
    const name = characteristic.name || 'Characteristic';
    let value = characteristic.value ?? '';
    if (characteristic.lower_bound !== undefined || characteristic.upper_bound !== undefined) {
      value = `${characteristic.lower_bound ?? ''}–${characteristic.upper_bound ?? ''}`;
    }
    const unit = characteristic.unit ? ` ${characteristic.unit}` : '';
    const suffix = value !== '' ? ` = ${value}${unit}` : '';
    container.appendChild(revisionTreeLine(`Characteristic: ${name}${suffix}`, 'secondary'));
  });
}

function renderRevisionTextualModel(model) {
  const textualRoot = document.getElementById('modelTextual');
  if (!textualRoot) return;
  const nodes = model.nodes || [];
  const drafts = model.drafts || [];
  const edges = model.edges || [];
  const byId = new Map(nodes.map(node => [node.id, node]));
  textualRoot.innerHTML = '';

  if (!nodes.length && !drafts.length) {
    const empty = document.createElement('div');
    empty.className = 'textual-empty';
    empty.textContent = 'Confirmed and temporary model elements will appear here as you work.';
    textualRoot.appendChild(empty);
    return;
  }

  const addSection = title => {
    const section = document.createElement('section');
    section.className = 'tree-section';
    const heading = document.createElement('h3');
    heading.textContent = title;
    section.appendChild(heading);
    textualRoot.appendChild(section);
    return section;
  };

  const goals = nodes.filter(node => node.type === 'OperationalCapability');
  if (goals.length) {
    const section = addSection('Goals');
    goals.forEach(goal => {
      const {item, children} = revisionTreeItem(goal.name || goal.id, 'Confirmed');
      revisionAppendCharacteristics(children, goal);
      section.appendChild(item);
    });
  }

  const participants = nodes.filter(node => ['OperationalActor', 'OperationalEntity'].includes(node.type));
  if (participants.length) {
    const section = addSection('Participants and actions');
    participants.forEach(participant => {
      const {item, children} = revisionTreeItem(
        participant.name || participant.id,
        revisionFriendlyType(participant.type)
      );
      revisionAppendCharacteristics(children, participant);

      const actionIds = edges
        .filter(edge => edge.type === 'PERFORMS' && edge.source === participant.id)
        .map(edge => edge.target);
      actionIds.forEach(actionId => {
        const action = byId.get(actionId);
        if (!action) return;
        const actionItem = revisionTreeItem(action.name || action.id, 'Action');
        revisionAppendCharacteristics(actionItem.children, action);

        edges
          .filter(edge => edge.type === 'SUPPORTS_CAPABILITY' && edge.source === actionId)
          .forEach(edge => {
            const goal = byId.get(edge.target);
            if (goal) actionItem.children.appendChild(
              revisionTreeLine(`Supports goal: ${goal.name || goal.id}`, 'secondary')
            );
          });

        edges
          .filter(edge => edge.type === 'OPERATIONAL_EXCHANGE' && edge.source === actionId)
          .forEach(edge => {
            const target = byId.get(edge.target);
            actionItem.children.appendChild(
              revisionTreeLine(`Exchange: ${edge.name || 'Exchange'} → ${target?.name || edge.target}`)
            );
          });

        children.appendChild(actionItem.item);
      });

      edges
        .filter(edge => edge.type === 'CONTAINS' && edge.target === participant.id)
        .forEach(edge => {
          const parent = byId.get(edge.source);
          children.appendChild(revisionTreeLine(`Part of: ${parent?.name || edge.source}`, 'secondary'));
        });
      edges
        .filter(edge => edge.type === 'LOCATED_IN' && edge.source === participant.id)
        .forEach(edge => {
          const location = byId.get(edge.target);
          children.appendChild(revisionTreeLine(`Located in: ${location?.name || edge.target}`, 'secondary'));
        });

      section.appendChild(item);
    });
  }

  const assignedActions = new Set(
    edges.filter(edge => edge.type === 'PERFORMS').map(edge => edge.target)
  );
  const unassignedActions = nodes.filter(
    node => node.type === 'OperationalActivity' && !assignedActions.has(node.id)
  );
  if (unassignedActions.length) {
    const section = addSection('Other actions');
    unassignedActions.forEach(action => {
      const {item, children} = revisionTreeItem(action.name || action.id, 'Action');
      revisionAppendCharacteristics(children, action);
      section.appendChild(item);
    });
  }

  const communicationEdges = edges.filter(edge => edge.type === 'COMMUNICATION_MEAN');
  if (communicationEdges.length) {
    const section = addSection('Communication');
    communicationEdges.forEach(edge => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      section.appendChild(revisionTreeLine(
        `${source?.name || edge.source} ↔ ${target?.name || edge.target}: ${edge.name || 'communication method'}`
      ));
    });
  }

  const decompositionEdges = edges.filter(edge => edge.type === 'DECOMPOSES');
  if (decompositionEdges.length) {
    const section = addSection('Decomposition');
    decompositionEdges.forEach(edge => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      section.appendChild(revisionTreeLine(
        `${source?.name || edge.source} ${revisionFriendlyRelation(edge.type)} ${target?.name || edge.target}`
      ));
    });
  }

  if (drafts.length) {
    const section = addSection('Temporary');
    drafts.forEach(draft => {
      const {item} = revisionTreeItem(draft.name || draft.id, 'Not yet confirmed', true);
      section.appendChild(item);
    });
  }
}
