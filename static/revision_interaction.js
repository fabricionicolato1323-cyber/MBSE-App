let revisionLastTurnsSignature = '';

function revisionTurnsSignature(turns) {
  return turns.map(turn => `${turn.id}:${turn.role}`).join('|');
}

function revisionLineKind(line) {
  const trimmed = line.trim();
  if (!trimmed) return 'spacer';
  if (trimmed.includes('?')) return 'question';
  if (/^\s+/.test(line)) return 'support';
  if (/^(Expected answer:|Example:|Answer only|Choose one|Describe |Name )/i.test(trimmed)) return 'support';
  return 'main';
}

function renderRevisionAssistantContent(bubble, content) {
  String(content || '').split('\n').forEach(line => {
    // Numbered terminal choices are represented by clickable controls instead.
    if (/^\s*\d+\.\s+/.test(line)) return;
    const kind = revisionLineKind(line);
    const element = document.createElement('div');
    element.className = `message-line ${kind}`;
    element.textContent = kind === 'spacer' ? '\u00a0' : line.trim();
    bubble.appendChild(element);
  });
}

function renderRevisionTurns(turns) {
  const chatRoot = document.getElementById('chat');
  const signature = revisionTurnsSignature(turns);
  if (signature === revisionLastTurnsSignature) return;
  revisionLastTurnsSignature = signature;
  chatRoot.innerHTML = '';

  turns.forEach(turn => {
    const row = document.createElement('div');
    row.className = `message-row ${turn.role}`;
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    if (turn.role === 'assistant') {
      renderRevisionAssistantContent(bubble, turn.content);
    } else {
      bubble.textContent = turn.content;
    }
    row.appendChild(bubble);
    chatRoot.appendChild(row);
  });
  chatRoot.scrollTop = chatRoot.scrollHeight;
}

function normalizeRevisionInteraction(interaction) {
  const allowed = new Set(['free_text', 'yes_no', 'choice', 'continue']);
  const raw = interaction && typeof interaction === 'object' ? interaction : {};
  const mode = allowed.has(raw.mode) ? raw.mode : 'free_text';
  let choices = Array.isArray(raw.choices)
    ? raw.choices.filter(item => item && String(item.label || '').trim())
    : [];
  if (mode === 'yes_no' && choices.length === 0) {
    choices = [{label: 'Yes', value: 'yes'}, {label: 'No', value: 'no'}];
  }
  if (mode === 'continue' && choices.length === 0) {
    choices = [{label: 'Continue', value: ''}];
  }
  return {mode, choices};
}

function inferRevisionStructuredInteraction(turns) {
  const latestAssistant = [...(turns || [])].reverse().find(turn => turn.role === 'assistant');
  const content = String(latestAssistant?.content || '');
  if (!content) return null;

  if (/\(\s*yes\s*\/\s*no\s*\)/i.test(content)) {
    return {
      mode: 'yes_no',
      choices: [{label: 'Yes', value: 'yes'}, {label: 'No', value: 'no'}]
    };
  }

  const choices = [];
  content.split('\n').forEach(line => {
    const match = line.match(/^\s*(\d+)\.\s+(.+?)\s*$/);
    if (match) choices.push({label: match[2].trim(), value: match[1]});
  });
  if (choices.length) return {mode: 'choice', choices};

  if (/Press Enter to return to the current question/i.test(content)) {
    return {mode: 'continue', choices: [{label: 'Continue', value: ''}]};
  }
  return null;
}

function interactionForRevisionUI(interaction, turns) {
  const normalized = normalizeRevisionInteraction(interaction);
  const visibleStructured = inferRevisionStructuredInteraction(turns);

  // Permanent UI contract: if the current prompt visibly offers a finite
  // choice, typing must never be required. Visible structure wins over an
  // inconsistent free-text protocol payload.
  if (visibleStructured && normalized.mode === 'free_text') {
    return visibleStructured;
  }
  if (
    visibleStructured?.mode === 'choice' &&
    normalized.mode === 'choice' &&
    normalized.choices.length === 0
  ) {
    return visibleStructured;
  }
  return normalized;
}

function renderRevisionInteraction(interaction, waiting, turns) {
  const quickRoot = document.getElementById('quickActions');
  const composerRoot = document.getElementById('composer');
  const normalized = interactionForRevisionUI(interaction, turns);
  activeInteractionMode = normalized.mode;
  quickRoot.innerHTML = '';
  quickRoot.className = 'quick-actions';

  const structured = waiting && normalized.mode !== 'free_text';
  const freeText = waiting && normalized.mode === 'free_text';
  quickRoot.hidden = !structured;
  composerRoot.hidden = !freeText;
  if (!structured) return;

  quickRoot.classList.add('structured-options');
  if (normalized.mode === 'yes_no') quickRoot.classList.add('binary-options');
  if (normalized.mode === 'continue') quickRoot.classList.add('continue-options');

  normalized.choices.forEach(choice => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = choice.label;
    button.disabled = !waiting || busy;
    button.addEventListener('click', () => sendValue(String(choice.value ?? ''), choice.label));
    quickRoot.appendChild(button);
  });
}

applyState = function revisedApplyState(state) {
  if (!state.session_id) return;
  if (activeSessionId && state.session_id !== activeSessionId) return;
  if (!activeSessionId) activeSessionId = state.session_id;

  const turns = state.turns || [];
  renderRevisionTurns(turns);
  renderRevisionTextualModel(state.model || {});
  renderDetails(state.model || {});

  const countRoot = document.getElementById('modelCount');
  const counts = state.model?.counts || {nodes: 0, edges: 0};
  const drafts = state.model?.drafts?.length || 0;
  countRoot.textContent = `${counts.nodes} items · ${counts.edges} links${drafts ? ` · ${drafts} temporary` : ''}`;

  if (startingNewModel && state.waiting && turns.length) {
    startingNewModel = false;
  }

  if (state.closed) {
    setBusy(true, 'Modeling session finished.');
  } else if (startingNewModel) {
    setBusy(true, 'Starting new model…');
  } else {
    setBusy(!state.waiting);
  }

  const waiting = Boolean(state.waiting) && !state.closed && !startingNewModel;
  renderRevisionInteraction(state.interaction || {mode: 'free_text', choices: []}, waiting, turns);
};

document.querySelectorAll('.tab-button').forEach(button => {
  button.addEventListener('click', () => {
    const tab = button.dataset.tab;
    document.querySelectorAll('.tab-button').forEach(item => {
      const selected = item === button;
      item.classList.toggle('active', selected);
      item.setAttribute('aria-selected', selected ? 'true' : 'false');
    });
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    const target = document.getElementById(`${tab}Tab`);
    if (target) target.classList.add('active');
  });
});
