let revisionLastTurnsSignature = '';
let revisionLastInteractionSignature = '';
let revisionRequestInFlight = false;
let revisionRequestSourceAssistantId = null;
let revisionCurrentAssistantId = null;

function revisionTurnsSignature(turns) {
  return turns.map(turn => `${turn.id}:${turn.role}`).join('|');
}

function revisionLatestAssistantTurn(turns) {
  for (let index = turns.length - 1; index >= 0; index -= 1) {
    if (turns[index]?.role === 'assistant') return turns[index];
  }
  return null;
}

function revisionLineKind(line) {
  const trimmed = line.trim();
  if (!trimmed) return 'spacer';
  if (trimmed.includes('?')) return 'question';
  if (/^\s+/.test(line)) return 'support';
  return 'main';
}

function revisionConciseLine(line) {
  return String(line || '')
    .replace(/\s*\(yes\/no\)\s*/ig, '')
    .trim();
}

function revisionShouldHideLine(line) {
  const text = String(line || '').trim();
  if (!text) return false;
  if (/^Expected answer:/i.test(text)) return true;
  if (/^Example:/i.test(text)) return true;
  if (/^Answer only ['\"]?yes['\"]? or ['\"]?no/i.test(text)) return true;
  if (/^Choose one of the numbers below/i.test(text)) return true;
  if (/^Select one of the options below/i.test(text)) return true;
  if (/^The app provides advisory classifications and validation checks\.?$/i.test(text)) return true;
  if (/^You remain responsible for confirming persistent model content\.?$/i.test(text)) return true;
  return false;
}

function revisionQuestionTools(canUndo = true) {
  const controls = document.createElement('div');
  controls.className = 'question-context-controls';

  const undo = document.createElement('button');
  undo.type = 'button';
  undo.className = 'question-icon-button';
  undo.title = 'Undo previous answer';
  undo.setAttribute('aria-label', 'Undo previous answer');
  undo.textContent = '↶';
  undo.disabled = !canUndo;
  undo.addEventListener('click', () => sendCommand('/undo'));

  const help = document.createElement('button');
  help.type = 'button';
  help.className = 'question-icon-button';
  help.title = 'Why this question?';
  help.setAttribute('aria-label', 'Why this question?');
  help.textContent = '?';
  help.addEventListener('click', () => sendCommand('/why'));

  controls.append(undo, help);
  return controls;
}

function renderRevisionAssistantContent(bubble, content) {
  String(content || '').split('\n').forEach(line => {
    if (/^\s*\d+\.\s+/.test(line)) return;
    if (revisionShouldHideLine(line)) return;
    const concise = revisionConciseLine(line);
    const kind = revisionLineKind(concise);
    const element = document.createElement('div');
    element.className = `message-line ${kind}`;
    element.textContent = kind === 'spacer' ? '\u00a0' : concise;
    bubble.appendChild(element);
  });
}

function revisionRevealActiveQuestion(chatRoot, activeRow) {
  if (!chatRoot || !activeRow) return;
  requestAnimationFrame(() => {
    const chatRect = chatRoot.getBoundingClientRect();
    const rowRect = activeRow.getBoundingClientRect();
    const padding = 12;

    if (rowRect.height > chatRect.height - padding * 2) {
      chatRoot.scrollTop += rowRect.top - chatRect.top - padding;
      return;
    }
    if (rowRect.top < chatRect.top + padding) {
      chatRoot.scrollTop += rowRect.top - chatRect.top - padding;
    } else if (rowRect.bottom > chatRect.bottom - padding) {
      chatRoot.scrollTop += rowRect.bottom - chatRect.bottom + padding;
    }
  });
}

function renderRevisionTurns(
  turns,
  {showQuestionTools = false, canUndo = true} = {}
) {
  const chatRoot = document.getElementById('chat');
  const signature = `${revisionTurnsSignature(turns)}:${showQuestionTools ? 'tools' : 'plain'}:${canUndo}`;
  if (signature === revisionLastTurnsSignature) return;
  revisionLastTurnsSignature = signature;
  chatRoot.innerHTML = '';

  const latestAssistant = revisionLatestAssistantTurn(turns);
  let activeRow = null;
  turns.forEach(turn => {
    const row = document.createElement('div');
    row.className = `message-row ${turn.role}`;
    row.dataset.turnId = turn.id;
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    if (turn.role === 'assistant') {
      renderRevisionAssistantContent(bubble, turn.content);
      if (latestAssistant?.id === turn.id) activeRow = row;
      if (showQuestionTools && latestAssistant?.id === turn.id) {
        bubble.classList.add('question-message-wrap');
        bubble.appendChild(revisionQuestionTools(canUndo));
      }
    } else {
      bubble.textContent = turn.content;
    }
    row.appendChild(bubble);
    chatRoot.appendChild(row);
  });

  revisionRevealActiveQuestion(chatRoot, activeRow);
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

function latestAssistantText(turns) {
  return String(revisionLatestAssistantTurn(turns)?.content || '');
}

function structuredFallbackFromAssistant(turns) {
  const text = latestAssistantText(turns);
  if (!text) return null;

  if (/\(yes\/no\)/i.test(text)) {
    return {
      mode: 'yes_no',
      choices: [{label: 'Yes', value: 'yes'}, {label: 'No', value: 'no'}]
    };
  }

  const matches = [...text.matchAll(/^\s*(\d+)\.\s+(.+?)\s*$/gm)];
  if (matches.length) {
    return {
      mode: 'choice',
      choices: matches.map(match => ({label: match[2].trim(), value: match[1]}))
    };
  }
  return null;
}

function effectiveRevisionInteraction(state) {
  const explicit = normalizeRevisionInteraction(state.interaction);
  const fallback = structuredFallbackFromAssistant(state.turns || []);
  if (fallback && explicit.mode === 'free_text') return fallback;
  if (fallback?.mode === 'choice' && explicit.mode === 'choice' && !explicit.choices.length) {
    return fallback;
  }
  return explicit;
}

function revisionInteractionSignature(interaction, waiting, locked) {
  return JSON.stringify({
    session: activeSessionId || '',
    mode: interaction.mode,
    choices: interaction.choices.map(choice => [
      String(choice.label ?? ''),
      String(choice.value ?? '')
    ]),
    waiting: Boolean(waiting),
    locked: Boolean(locked),
    busy: Boolean(busy)
  });
}

function renderRevisionInteraction(interaction, waiting, {locked = false} = {}) {
  const quickRoot = document.getElementById('quickActions');
  const composerRoot = document.getElementById('composer');
  const normalized = normalizeRevisionInteraction(interaction);
  activeInteractionMode = normalized.mode;

  const structured = waiting && normalized.mode !== 'free_text';
  const freeText = waiting && normalized.mode === 'free_text';
  const signature = revisionInteractionSignature(normalized, waiting, locked);
  const expectedButtonCount = structured ? normalized.choices.length : 0;
  const stableStructuredDom = !structured || quickRoot.childElementCount === expectedButtonCount;

  quickRoot.hidden = !structured;
  composerRoot.hidden = !freeText;

  if (
    signature === revisionLastInteractionSignature &&
    stableStructuredDom
  ) {
    return;
  }
  revisionLastInteractionSignature = signature;

  quickRoot.innerHTML = '';
  quickRoot.className = 'quick-actions';
  if (!structured) return;

  quickRoot.classList.add('structured-options');
  if (normalized.mode === 'yes_no') quickRoot.classList.add('binary-options');
  if (normalized.mode === 'continue') quickRoot.classList.add('continue-options');

  normalized.choices.forEach(choice => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = choice.label;
    if (/^\+\s*Add new/i.test(choice.label)) button.classList.add('add-new-option');
    button.disabled = !waiting || busy || locked;
    button.addEventListener('click', () =>
      sendValue(String(choice.value ?? ''), choice.label)
    );
    quickRoot.appendChild(button);
  });
}

function revisionLockControls() {
  document.querySelectorAll('#quickActions button, #composer button, #composer textarea, .question-icon-button')
    .forEach(element => { element.disabled = true; });
}

function revisionBeginRequest() {
  if (revisionRequestInFlight) return false;
  revisionRequestInFlight = true;
  revisionRequestSourceAssistantId = revisionCurrentAssistantId;
  revisionLockControls();
  setBusy(true, 'Processing…');
  return true;
}

function revisionEndRequestForError(message) {
  revisionRequestInFlight = false;
  revisionRequestSourceAssistantId = null;
  setBusy(false, message);
}

sendValue = async function revisedSendValue(value, displayValue = null) {
  if (busy || !revisionBeginRequest()) return;

  try {
    const response = await fetch('/api/input', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({value, display_value: displayValue})
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      revisionEndRequestForError(data.error || 'The input could not be sent.');
      return;
    }

    input.value = '';
    await pollState({force: true});
  } catch (error) {
    revisionEndRequestForError('Connection to the local app was interrupted.');
  }
};

sendCommand = async function revisedSendCommand(command) {
  if (busy || !revisionBeginRequest()) return;

  try {
    const response = await fetch('/api/command', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({command})
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      revisionEndRequestForError(data.error || 'The command could not be sent.');
      return;
    }

    await pollState({force: true});
  } catch (error) {
    revisionEndRequestForError('Connection to the local app was interrupted.');
  }
};

function revisionClosedStateMessage(state) {
  const fullText = (state.turns || []).map(turn => turn.content || '').join('\n');
  if (/Modeling session finished\./i.test(fullText)) {
    return 'Modeling session finished.';
  }
  return 'The local modeling worker stopped unexpectedly. Start a new model or check worker.log.';
}

applyState = function revisedApplyState(state) {
  if (!state.session_id) return;
  if (activeSessionId && state.session_id !== activeSessionId) return;
  if (!activeSessionId) activeSessionId = state.session_id;

  const latestAssistant = revisionLatestAssistantTurn(state.turns || []);
  const latestAssistantId = latestAssistant?.id || null;
  revisionCurrentAssistantId = latestAssistantId;

  if (
    revisionRequestInFlight &&
    latestAssistantId &&
    revisionRequestSourceAssistantId &&
    latestAssistantId !== revisionRequestSourceAssistantId
  ) {
    revisionRequestInFlight = false;
    revisionRequestSourceAssistantId = null;
  }

  const waiting = Boolean(state.waiting) && !state.closed && !startingNewModel;
  const usableWaiting = waiting && !revisionRequestInFlight;
  const interaction = effectiveRevisionInteraction(state);

  renderRevisionTurns(state.turns || [], {
    showQuestionTools: usableWaiting && interaction.mode !== 'continue',
    canUndo: Boolean(state.can_undo)
  });
  renderRevisionTextualModel(state.model || {});
  renderRevisionDetails(state.model || {});

  const countRoot = document.getElementById('modelCount');
  const counts = state.model?.counts || {nodes: 0, edges: 0};
  const drafts = state.model?.drafts?.length || 0;
  countRoot.textContent = `${counts.nodes} items${drafts ? ` · ${drafts} temporary` : ''}`;

  if (startingNewModel && state.waiting && (state.turns || []).length) {
    startingNewModel = false;
  }

  if (state.closed) {
    setBusy(true, revisionClosedStateMessage(state));
  } else if (startingNewModel) {
    setBusy(true, 'Starting new model…');
  } else if (revisionRequestInFlight) {
    setBusy(true, 'Processing…');
  } else {
    setBusy(!state.waiting);
  }

  renderRevisionInteraction(
    interaction,
    waiting,
    {locked: revisionRequestInFlight}
  );

  const chatRoot = document.getElementById('chat');
  const activeRow = chatRoot?.querySelector(`.message-row[data-turn-id="${latestAssistantId}"]`);
  revisionRevealActiveQuestion(chatRoot, activeRow);
};

document.querySelectorAll('.tab-button').forEach(button => {
  button.addEventListener('click', () => {
    const tab = button.dataset.tab;
    document.querySelectorAll('.tab-button').forEach(item => {
      const selected = item === button;
      item.classList.toggle('active', selected);
      item.setAttribute('aria-selected', selected ? 'true' : 'false');
    });
    document.querySelectorAll('.tab-content').forEach(content =>
      content.classList.remove('active')
    );
    const target = document.getElementById(`${tab}Tab`);
    if (target) target.classList.add('active');
  });
});
