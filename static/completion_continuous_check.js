(() => {
  function countCharacteristics(nodes) {
    return nodes.reduce(
      (total, node) => total + (Array.isArray(node.characteristics) ? node.characteristics.length : 0),
      0
    );
  }

  function completionItems(model) {
    const nodes = Array.isArray(model?.nodes) ? model.nodes : [];
    const edges = Array.isArray(model?.edges) ? model.edges : [];
    const goals = nodes.filter(node => node.type === 'OperationalCapability');
    const participants = nodes.filter(node =>
      ['OperationalActor', 'OperationalEntity'].includes(node.type)
    );
    const actions = nodes.filter(node => node.type === 'OperationalActivity');

    const goalIds = new Set(goals.map(node => node.id));
    const participantIds = new Set(participants.map(node => node.id));
    const actionIds = new Set(actions.map(node => node.id));

    const performs = edges.filter(edge =>
      edge.type === 'PERFORMS' &&
      participantIds.has(edge.source) &&
      actionIds.has(edge.target)
    );
    const ownedActions = new Set(performs.map(edge => edge.target));
    const activeOwners = new Set(performs.map(edge => edge.source));

    const supportsGoal = edges.filter(edge =>
      edge.type === 'SUPPORTS_CAPABILITY' &&
      actionIds.has(edge.source) &&
      goalIds.has(edge.target)
    );
    const goalLinkedActions = new Set(supportsGoal.map(edge => edge.source));

    const exchanges = edges.filter(edge => edge.type === 'OPERATIONAL_EXCHANGE');
    const communication = edges.filter(edge => edge.type === 'COMMUNICATION_MEAN');
    const characteristicCount = countCharacteristics(nodes);

    let ownershipRatio = 0;
    if (actions.length && participants.length) {
      ownershipRatio = Math.min(
        1,
        ((ownedActions.size / actions.length) + (activeOwners.size / participants.length)) / 2
      );
    }

    // The old conversational Check model required every activity to contribute
    // to a goal. Completion now owns that check continuously. Keep the existing
    // 20-point activity category, but award only half of it for merely having
    // activities; the other half requires every activity to support a goal.
    const goalLinkRatio = actions.length ? goalLinkedActions.size / actions.length : 0;
    const activityRatio = actions.length ? .5 + .5 * goalLinkRatio : 0;
    let activityDetail = 'Add the actions that must occur operationally.';
    if (actions.length) {
      activityDetail = goals.length
        ? `${actions.length} defined · ${goalLinkedActions.size}/${actions.length} connected to an operational goal`
        : `${actions.length} defined · add an operational goal and connect the activities to it`;
    }

    return [
      {
        label: 'Operational goal',
        weight: 15,
        ratio: goals.length ? 1 : 0,
        detail: goals.length ? `${goals.length} defined` : 'Add at least one operational goal.'
      },
      {
        label: 'Participants / context',
        weight: 15,
        ratio: participants.length ? 1 : 0,
        detail: participants.length ? `${participants.length} defined` : 'Add the people, organizations, systems or context involved.'
      },
      {
        label: 'Operational activities',
        weight: 20,
        ratio: activityRatio,
        detail: activityDetail
      },
      {
        label: 'Activity ownership',
        weight: 15,
        ratio: ownershipRatio,
        detail: !actions.length || !participants.length
          ? 'Activities and participants are needed before ownership can be checked.'
          : `${ownedActions.size}/${actions.length} activities assigned · ${activeOwners.size}/${participants.length} participants with activities`
      },
      {
        label: 'Operational interactions',
        weight: 15,
        ratio: exchanges.length ? 1 : 0,
        detail: exchanges.length ? `${exchanges.length} interaction(s) defined` : 'Add exchanges between operational activities when information or material flows.'
      },
      {
        label: 'Communication means',
        weight: 10,
        ratio: communication.length ? 1 : 0,
        detail: communication.length ? `${communication.length} communication link(s) defined` : 'Add how relevant participants communicate.'
      },
      {
        label: 'Characteristics / limits',
        weight: 10,
        ratio: characteristicCount ? 1 : 0,
        detail: characteristicCount ? `${characteristicCount} characteristic(s) captured` : 'Add quantitative limits, ranges or other relevant characteristics.'
      }
    ];
  }

  function renderContinuousCompletion(model) {
    const percentRoot = document.getElementById('completionPercent');
    const barRoot = document.getElementById('completionBarFill');
    const listRoot = document.getElementById('completionList');
    if (!percentRoot || !barRoot || !listRoot) return;

    const items = completionItems(model || {});
    const percent = Math.round(
      items.reduce((sum, item) => sum + item.weight * item.ratio, 0)
    );

    percentRoot.textContent = `${percent}%`;
    barRoot.style.width = `${percent}%`;
    listRoot.dataset.continuousCheck = 'true';
    listRoot.innerHTML = '';

    items.forEach(item => {
      const state = item.ratio >= .999 ? 'done' : item.ratio > 0 ? 'partial' : 'missing';
      const row = document.createElement('div');
      row.className = `completion-item ${state}`;

      const icon = document.createElement('span');
      icon.className = 'completion-item-icon';
      icon.textContent = state === 'done' ? '✓' : state === 'partial' ? '◐' : '·';

      const copy = document.createElement('div');
      copy.className = 'completion-item-copy';
      const title = document.createElement('strong');
      title.textContent = item.label;
      const detail = document.createElement('span');
      detail.textContent = item.detail;
      copy.append(title, detail);

      row.append(icon, copy);
      listRoot.appendChild(row);
    });
  }

  function install() {
    if (typeof applyState === 'function') {
      const baseApplyState = applyState;
      applyState = function continuousCompletionApplyState(state) {
        baseApplyState(state);
        renderContinuousCompletion(state?.model || {});
      };
    }

    if (typeof clearRenderedSession === 'function') {
      const baseClearRenderedSession = clearRenderedSession;
      clearRenderedSession = function continuousCompletionClearRenderedSession() {
        baseClearRenderedSession();
        renderContinuousCompletion({nodes: [], edges: []});
      };
    }

    renderContinuousCompletion({nodes: [], edges: []});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install, {once: true});
  } else {
    install();
  }
})();
