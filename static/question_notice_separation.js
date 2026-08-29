function revisionTrimSeparatedContent(lines) {
  const copy = [...lines];
  while (copy.length && !String(copy[0] || '').trim()) copy.shift();
  while (copy.length && !String(copy[copy.length - 1] || '').trim()) copy.pop();
  return copy.join('\n');
}

function revisionHasVisibleSeparatedContent(content) {
  return String(content || '').split('\n').some(line => {
    if (/^\s*\d+\.\s+/.test(line)) return false;
    if (revisionShouldHideLine(line)) return false;
    return Boolean(revisionConciseLine(line));
  });
}

function revisionSplitAssistantQuestion(content) {
  const lines = String(content || '').split('\n');
  let questionIndex = -1;

  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index];
    if (/^\s*\d+\.\s+/.test(line)) continue;
    if (revisionShouldHideLine(line)) continue;
    const concise = revisionConciseLine(line);
    if (revisionLineKind(concise) === 'question') {
      questionIndex = index;
      break;
    }
  }

  if (questionIndex <= 0) {
    return {notice: '', question: String(content || '')};
  }

  const notice = revisionTrimSeparatedContent(lines.slice(0, questionIndex));
  const question = revisionTrimSeparatedContent(lines.slice(questionIndex));

  if (!revisionHasVisibleSeparatedContent(notice)) {
    return {notice: '', question: String(content || '')};
  }

  return {notice, question};
}

function revisionAppendAssistantRow(chatRoot, turn, content, options = {}) {
  const row = document.createElement('div');
  row.className = `message-row assistant${options.notice ? ' notice-row' : ''}`;
  row.dataset.turnId = options.notice ? `${turn.id}:notice` : turn.id;

  const bubble = document.createElement('div');
  bubble.className = `message-bubble${options.notice ? ' notice-bubble' : ''}`;
  renderRevisionAssistantContent(bubble, content);

  if (options.tools) {
    bubble.classList.add('question-message-wrap');
    bubble.appendChild(revisionQuestionTools(options.canUndo));
  }

  row.appendChild(bubble);
  chatRoot.appendChild(row);
  return row;
}

renderRevisionTurns = function separatedRevisionTurns(
  turns,
  {showQuestionTools = false, canUndo = true} = {}
) {
  const chatRoot = document.getElementById('chat');
  const signature = `${revisionTurnsSignature(turns)}:${showQuestionTools ? 'tools' : 'plain'}:${canUndo}:separated-notices`;
  if (signature === revisionLastTurnsSignature) return;
  revisionLastTurnsSignature = signature;
  chatRoot.innerHTML = '';

  const latestAssistant = revisionLatestAssistantTurn(turns);
  let activeRow = null;

  turns.forEach(turn => {
    if (turn.role !== 'assistant') {
      const row = document.createElement('div');
      row.className = `message-row ${turn.role}`;
      row.dataset.turnId = turn.id;
      const bubble = document.createElement('div');
      bubble.className = 'message-bubble';
      bubble.textContent = turn.content;
      row.appendChild(bubble);
      chatRoot.appendChild(row);
      return;
    }

    const split = revisionSplitAssistantQuestion(turn.content);
    if (split.notice) {
      revisionAppendAssistantRow(chatRoot, turn, split.notice, {notice: true});
    }

    const isLatest = latestAssistant?.id === turn.id;
    const questionRow = revisionAppendAssistantRow(
      chatRoot,
      turn,
      split.question,
      {
        tools: showQuestionTools && isLatest,
        canUndo,
      }
    );

    if (isLatest) activeRow = questionRow;
  });

  revisionRevealActiveQuestion(chatRoot, activeRow);
};
