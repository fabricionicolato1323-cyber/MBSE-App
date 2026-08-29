function revisionRelationshipAwareModel(model) {
  const nodes = model.nodes || [];
  const edges = model.edges || [];
  const byId = new Map(nodes.map(node => [node.id, node]));

  // Any confirmed model node used as the target of LOCATED_IN is a visual
  // location/context parent. This deliberately does not depend on how the
  // browser previously classified the target for presentation.
  const locationTargets = new Set(
    edges
      .filter(edge => edge.type === 'LOCATED_IN' && byId.has(edge.target))
      .map(edge => edge.target)
  );

  const goalsByAction = new Map();
  edges
    .filter(edge => edge.type === 'SUPPORTS_CAPABILITY')
    .forEach(edge => {
      const goal = byId.get(edge.target);
      if (!goal) return;
      if (!goalsByAction.has(edge.source)) goalsByAction.set(edge.source, []);
      goalsByAction.get(edge.source).push(goal.name || goal.id);
    });

  const patchedNodes = nodes.map(node => {
    let patched = node;

    if (
      locationTargets.has(node.id) &&
      !['OperationalCapability', 'OperationalActivity'].includes(node.type)
    ) {
      // The textual renderer treats participant/context nodes as eligible tree
      // parents. Normalize a location target only for this derived view.
      patched = {...patched, type: 'OperationalEntity'};
    }

    if (node.type === 'OperationalActivity') {
      const goalNames = goalsByAction.get(node.id) || [];
      const hasDerivedLine = (node.characteristics || []).some(
        item => String(item.name || '').trim().toLowerCase() === 'contributes to'
      );
      if (goalNames.length && !hasDerivedLine) {
        patched = {
          ...patched,
          characteristics: [
            ...(node.characteristics || []),
            {
              name: 'Contributes to',
              value_type: 'text',
              value: goalNames.join(', '),
              derived_from_relation: true
            }
          ]
        };
      }
    }

    return patched;
  });

  return {...model, nodes: patchedNodes};
}

const revisionBaseTextualRelationshipRenderer = renderRevisionTextualModel;
renderRevisionTextualModel = function relationshipAwareTextualRenderer(model) {
  return revisionBaseTextualRelationshipRenderer(revisionRelationshipAwareModel(model));
};

const revisionBaseDetailsRelationshipRenderer = renderRevisionDetails;
renderRevisionDetails = function relationshipAwareDetailsRenderer(model) {
  return revisionBaseDetailsRelationshipRenderer(revisionRelationshipAwareModel(model));
};
