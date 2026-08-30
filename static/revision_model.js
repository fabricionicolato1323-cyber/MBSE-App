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

function revisionTreeItem(title, temporary = false) {
  const item = document.createElement('div');
  item.className = `tree-item${temporary ? ' temporary' : ''}`;
  const name = document.createElement('div');
  name.className = 'tree-item-name';
  name.textContent = title;
  item.appendChild(name);
  const children = document.createElement('div');
  children.className = 'tree-children';
  item.appendChild(children);
  return {item, children};
}

function revisionCharacteristicText(characteristic) {
  const name = characteristic.name || 'Characteristic';
  let value = characteristic.value ?? '';
  if (characteristic.lower_bound !== undefined || characteristic.upper_bound !== undefined) {
    value = `${characteristic.lower_bound ?? ''}–${characteristic.upper_bound ?? ''}`;
  }
  const unit = characteristic.unit ? ` ${characteristic.unit}` : '';
  return value !== '' ? `${name}: ${value}${unit}` : name;
}

function revisionAppendCharacteristics(container, node) {
  if (!Array.isArray(node.characteristics)) return;
  node.characteristics.forEach(characteristic => {
    container.appendChild(
      revisionTreeLine(revisionCharacteristicText(characteristic), 'secondary')
    );
  });
}

function revisionExchangeTreeItem(edge, target) {
  const exchange = edge.name || 'Exchange';
  const tree = revisionTreeItem(`${exchange} → ${target?.name || edge.target}`);
  tree.item.classList.add('operational-exchange-tree-item');
  tree.item.dataset.exchangeSource = String(edge.source || '');
  tree.item.dataset.exchangeTarget = String(edge.target || '');
  tree.item.dataset.exchangeName = String(edge.name || '');
  return tree;
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
    empty.textContent = 'The model will appear here as you build it.';
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
    const section = addSection(goals.length === 1 ? 'Goal' : 'Goals');
    goals.forEach(goal => {
      const {item, children} = revisionTreeItem(goal.name || goal.id);
      revisionAppendCharacteristics(children, goal);
      section.appendChild(item);
    });
  }

  const participants = nodes.filter(node =>
    ['OperationalActor', 'OperationalEntity'].includes(node.type)
  );
  if (participants.length) {
    const section = addSection('Participants');
    const participantIds = new Set(participants.map(participant => participant.id));
    const locationParentById = new Map();
    const locationChildrenById = new Map();

    edges
      .filter(edge =>
        edge.type === 'LOCATED_IN' &&
        participantIds.has(edge.source) &&
        participantIds.has(edge.target) &&
        edge.source !== edge.target
      )
      .forEach(edge => {
        // A participant is displayed under its first explicit participant/context location.
        // Additional LOCATED_IN relations remain visible as secondary information.
        if (!locationParentById.has(edge.source)) {
          locationParentById.set(edge.source, edge.target);
          if (!locationChildrenById.has(edge.target)) {
            locationChildrenById.set(edge.target, []);
          }
          locationChildrenById.get(edge.target).push(edge.source);
        }
      });

    const renderedParticipants = new Set();

    const renderParticipant = (participant, ancestry = new Set()) => {
      if (!participant || ancestry.has(participant.id)) return null;

      const {item, children} = revisionTreeItem(participant.name || participant.id);
      revisionAppendCharacteristics(children, participant);

      const actionIds = edges
        .filter(edge => edge.type === 'PERFORMS' && edge.source === participant.id)
        .map(edge => edge.target);

      actionIds.forEach(actionId => {
        const action = byId.get(actionId);
        if (!action) return;

        const actionItem = revisionTreeItem(action.name || action.id);
        revisionAppendCharacteristics(actionItem.children, action);

        edges
          .filter(edge => edge.type === 'OPERATIONAL_EXCHANGE' && edge.source === actionId)
          .forEach(edge => {
            const target = byId.get(edge.target);
            const exchangeItem = revisionExchangeTreeItem(edge, target);
            actionItem.children.appendChild(exchangeItem.item);
          });

        children.appendChild(actionItem.item);
      });

      // Composition/organization remains visible even when location is expressed
      // by the visual hierarchy. For example, "Part of Facility" is still useful
      // information about a receptionist nested under Facility.
      edges
        .filter(edge => edge.type === 'CONTAINS' && edge.target === participant.id)
        .forEach(edge => {
          const parent = byId.get(edge.source);
          children.appendChild(
            revisionTreeLine(`Part of ${parent?.name || edge.source}`, 'secondary')
          );
        });

      const hierarchyParentId = locationParentById.get(participant.id);
      edges
        .filter(edge =>
          edge.type === 'LOCATED_IN' &&
          edge.source === participant.id &&
          edge.target !== hierarchyParentId
        )
        .forEach(edge => {
          const location = byId.get(edge.target);
          children.appendChild(
            revisionTreeLine(`In ${location?.name || edge.target}`, 'secondary')
          );
        });

      const nextAncestry = new Set(ancestry);
      nextAncestry.add(participant.id);
      (locationChildrenById.get(participant.id) || []).forEach(childId => {
        const child = byId.get(childId);
        const childItem = renderParticipant(child, nextAncestry);
        if (childItem) children.appendChild(childItem);
      });

      renderedParticipants.add(participant.id);
      return item;
    };

    const roots = participants.filter(participant => {
      const parentId = locationParentById.get(participant.id);
      return !parentId || !participantIds.has(parentId);
    });

    roots.forEach(participant => {
      const item = renderParticipant(participant);
      if (item) section.appendChild(item);
    });

    // Defensive fallback for malformed/cyclic location data: never hide a participant.
    participants
      .filter(participant => !renderedParticipants.has(participant.id))
      .forEach(participant => {
        const item = renderParticipant(participant);
        if (item) section.appendChild(item);
      });
  }

  const communication = edges.filter(edge => edge.type === 'COMMUNICATION_MEAN');
  if (communication.length) {
    const section = addSection('Communication');
    communication.forEach(edge => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      section.appendChild(
        revisionTreeLine(
          `${source?.name || edge.source} ↔ ${target?.name || edge.target}: ` +
          `${edge.name || 'communication method'}`
        )
      );
    });
  }

  const decomposition = edges.filter(edge => edge.type === 'DECOMPOSES');
  if (decomposition.length) {
    const section = addSection('Breakdown');
    decomposition.forEach(edge => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      section.appendChild(
        revisionTreeLine(
          `${source?.name || edge.source} → ${target?.name || edge.target}`
        )
      );
    });
  }

  if (drafts.length) {
    const section = addSection('Temporary');
    drafts.forEach(draft => {
      const {item} = revisionTreeItem(draft.name || draft.id, true);
      section.appendChild(item);
    });
  }
}

function revisionDetailRow(label, value) {
  const row = document.createElement('div');
  row.className = 'detail-row';
  const key = document.createElement('span');
  key.className = 'detail-key';
  key.textContent = label;
  const val = document.createElement('span');
  val.className = 'detail-value';
  val.textContent = String(value);
  row.append(key, val);
  return row;
}

function renderRevisionDetails(model) {
  const details = document.getElementById('modelDetails');
  if (!details) return;

  const nodes = [...(model.nodes || []), ...(model.drafts || [])];
  const edges = model.edges || [];
  details.innerHTML = '';

  if (!nodes.length) {
    details.textContent = 'No model details yet.';
    return;
  }

  nodes.forEach(node => {
    const card = document.createElement('section');
    card.className = `detail-item ${node.status === 'temporary' ? 'temporary' : ''}`;

    const name = document.createElement('div');
    name.className = 'detail-name';
    name.textContent = node.name || node.id;
    card.appendChild(name);

    card.appendChild(revisionDetailRow('Type', revisionFriendlyType(node.type)));
    card.appendChild(
      revisionDetailRow('Status', node.status === 'temporary' ? 'Temporary' : 'Confirmed')
    );

    const metadata = [
      ['Nature', node.nature],
      ['Classification source', node.classification_source],
      ['Evidence', node.classification_evidence],
      ['Reason', node.classification_reason],
    ];
    metadata.forEach(([label, value]) => {
      if (value) card.appendChild(revisionDetailRow(label, value));
    });

    if (Array.isArray(node.characteristics)) {
      node.characteristics.forEach(characteristic => {
        card.appendChild(
          revisionDetailRow('Characteristic', revisionCharacteristicText(characteristic))
        );
      });
    }

    details.appendChild(card);
  });

  if (edges.length) {
    const heading = document.createElement('h3');
    heading.className = 'detail-section-title';
    heading.textContent = 'Connections';
    details.appendChild(heading);

    const byId = new Map((model.nodes || []).map(node => [node.id, node]));
    edges.forEach(edge => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      const card = document.createElement('section');
      card.className = 'detail-item';
      const title = document.createElement('div');
      title.className = 'detail-name';
      title.textContent = edge.name || revisionFriendlyRelation(edge.type);
      card.appendChild(title);
      card.appendChild(
        revisionDetailRow(
          'Connection',
          `${source?.name || edge.source} → ${target?.name || edge.target}`
        )
      );
      card.appendChild(
        revisionDetailRow('Type', revisionFriendlyRelation(edge.type))
      );
      details.appendChild(card);
    });
  }
}