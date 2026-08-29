const revisionChoiceHelpDefinitions = Object.freeze({
  'Person / role': 'A human participant or operational role that can perform actions.',
  'Organization, group, facility or other participant': 'A non-person participant or context element involved in the operation.',
  'Organization': 'A formally organized body, such as a company, agency, or institution.',
  'Organizational unit': 'A department, division, branch, or other unit inside a larger organization.',
  'Team or collective': 'A group of people acting together without needing to be a formal organization.',
  'Existing external technical system': 'A technical system that already exists outside the system being modeled and participates in the operation.',
  'Infrastructure or facility': 'A physical place or infrastructure element used in the operation, such as a site, building, or network.',
  'External operational service': 'A service provided externally that participates in or supports the operation.',
  'Population or community': 'A group of people considered collectively because they are affected by or involved in the operation.',
  'Environmental participant': 'A natural or environmental element that affects or participates in the operation, such as weather, terrain, water, or wildlife.',
  'Environmental component': 'A natural or environmental element that affects or participates in the operation, such as weather, terrain, water, or wildlife.',
  'Other / not yet specified': 'Use this when none of the available categories clearly describes the participant yet.',
  'Use suggested classification': 'Accept the current advisory classification for this participant.',
  'Ask AI for another opinion': 'Ask the active AI model for advisory classification help without changing the model automatically.',
  'Do not add this as a participant': 'Reject this candidate and leave it out of the model.',
  'Single numeric value': 'One measured or specified number, optionally with a unit and comparison operator.',
  'Single percentage value': 'One value expressed as a percentage, with an optional comparison operator.',
  'Numeric range': 'A lower and upper numeric boundary, each of which can be inclusive or exclusive.',
  'Percentage range': 'A lower and upper percentage boundary, each of which can be inclusive or exclusive.',
  'Text value': 'A descriptive characteristic expressed as text rather than a number.',
  'Exactly (=)': 'The characteristic is intended to equal this value.',
  'At least (≥)': 'The characteristic may equal this value or be greater than it.',
  'More than (>)': 'The characteristic must be strictly greater than this value.',
  'At most (≤)': 'The characteristic may equal this value or be less than it.',
  'Less than (<)': 'The characteristic must be strictly less than this value.',
  'Include the lower bound (≥)': 'The lower boundary value itself is allowed.',
  'Exclude the lower bound (>)': 'The value must be strictly above the lower boundary.',
  'Include the upper bound (≤)': 'The upper boundary value itself is allowed.',
  'Exclude the upper bound (<)': 'The value must be strictly below the upper boundary.',
  'Yes': 'Choose Yes to accept or continue with what the current question proposes.',
  'No': 'Choose No to decline or skip what the current question proposes.',
  'Continue': 'Continue from the current information screen to the modeling flow.'
});

let revisionChoiceTooltipPinnedButton = null;

function revisionChoiceHelpText(choice) {
  const label = String(choice?.label || '').trim();
  if (!label) return 'Select this option if it best matches what you mean.';
  if (revisionChoiceHelpDefinitions[label]) return revisionChoiceHelpDefinitions[label];

  if (/^\+\s*Add new action/i.test(label)) {
    return 'Create a new action first, then return to this selection.';
  }
  if (/^\+\s*Add new participant(?:\s*\/\s*context)?/i.test(label)) {
    return 'Create a new participant or context element first, then return to this selection.';
  }
  if (/^\+\s*Add new goal/i.test(label)) {
    return 'Create a new operational goal first, then return to this selection.';
  }
  if (/^Goal:/i.test(label)) {
    return 'An existing goal in the current model. Select it when this item contributes to that outcome.';
  }
  if (/^Action:/i.test(label)) {
    return 'An existing action in the current model. Select it when the current relationship or characteristic applies to that action.';
  }
  if (/^Participant\s*\/\s*context:/i.test(label)) {
    return 'An existing participant or context element in the current model.';
  }
  if (/^Participant:/i.test(label)) {
    return 'An existing participant in the current model.';
  }
  if (/^Interaction:/i.test(label)) {
    return 'An existing interaction between actions in the current model.';
  }
  if (/^Communication/i.test(label)) {
    return 'A communication-related option describing how participants exchange information.';
  }

  return 'Select this option if it best matches the meaning you intend for this step.';
}

function revisionEnsureChoiceTooltip() {
  let tooltip = document.getElementById('choiceHelpTooltip');
  if (tooltip) return tooltip;

  tooltip = document.createElement('div');
  tooltip.id = 'choiceHelpTooltip';
  tooltip.className = 'choice-help-tooltip';
  tooltip.setAttribute('role', 'tooltip');
  tooltip.hidden = true;
  document.body.appendChild(tooltip);
  return tooltip;
}

function revisionPositionChoiceTooltip(button, tooltip) {
  const rect = button.getBoundingClientRect();
  const margin = 10;
  const maxLeft = Math.max(margin, window.innerWidth - tooltip.offsetWidth - margin);
  const preferredLeft = rect.right - tooltip.offsetWidth;
  const left = Math.min(Math.max(margin, preferredLeft), maxLeft);
  let top = rect.top - tooltip.offsetHeight - 8;

  if (top < margin) {
    top = rect.bottom + 8;
  }

  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${Math.max(margin, top)}px`;
}

function revisionShowChoiceTooltip(button, {pinned = false} = {}) {
  const help = String(button?.dataset?.choiceHelp || '').trim();
  if (!help) return;

  const tooltip = revisionEnsureChoiceTooltip();
  tooltip.textContent = help;
  tooltip.hidden = false;
  tooltip.dataset.pinned = pinned ? 'true' : 'false';
  revisionChoiceTooltipPinnedButton = pinned ? button : revisionChoiceTooltipPinnedButton;
  requestAnimationFrame(() => revisionPositionChoiceTooltip(button, tooltip));
}

function revisionHideChoiceTooltip({force = false} = {}) {
  const tooltip = document.getElementById('choiceHelpTooltip');
  if (!tooltip) return;
  if (!force && tooltip.dataset.pinned === 'true') return;
  tooltip.hidden = true;
  tooltip.dataset.pinned = 'false';
  revisionChoiceTooltipPinnedButton = null;
}

function revisionCreateChoiceHelpButton(choice) {
  const helpButton = document.createElement('button');
  helpButton.type = 'button';
  helpButton.className = 'choice-help-button';
  helpButton.textContent = '?';
  helpButton.dataset.choiceHelp = revisionChoiceHelpText(choice);
  helpButton.setAttribute('aria-label', `Help for ${choice.label}`);
  helpButton.setAttribute('aria-expanded', 'false');

  helpButton.addEventListener('mouseenter', () => {
    if (revisionChoiceTooltipPinnedButton !== helpButton) {
      revisionShowChoiceTooltip(helpButton);
    }
  });
  helpButton.addEventListener('mouseleave', () => {
    if (revisionChoiceTooltipPinnedButton !== helpButton) {
      revisionHideChoiceTooltip();
    }
  });
  helpButton.addEventListener('focus', () => revisionShowChoiceTooltip(helpButton));
  helpButton.addEventListener('blur', () => {
    if (revisionChoiceTooltipPinnedButton !== helpButton) revisionHideChoiceTooltip();
  });
  helpButton.addEventListener('click', event => {
    event.preventDefault();
    event.stopPropagation();
    const wasPinned = revisionChoiceTooltipPinnedButton === helpButton;
    revisionHideChoiceTooltip({force: true});
    document.querySelectorAll('.choice-help-button[aria-expanded="true"]')
      .forEach(item => item.setAttribute('aria-expanded', 'false'));
    if (!wasPinned) {
      revisionChoiceTooltipPinnedButton = helpButton;
      helpButton.setAttribute('aria-expanded', 'true');
      revisionShowChoiceTooltip(helpButton, {pinned: true});
    }
  });

  return helpButton;
}

revisionSetStructuredButtonsEnabled = function choiceHelpSetStructuredButtonsEnabled(quickRoot, enabled) {
  quickRoot.querySelectorAll('.choice-option-button').forEach(button => {
    button.disabled = !enabled;
  });
  quickRoot.querySelectorAll('.choice-help-button').forEach(button => {
    button.disabled = false;
  });
};

renderRevisionInteraction = function choiceHelpRenderRevisionInteraction(
  interaction,
  waiting,
  {locked = false} = {}
) {
  const quickRoot = document.getElementById('quickActions');
  const composerRoot = document.getElementById('composer');
  const normalized = normalizeRevisionInteraction(interaction);
  activeInteractionMode = normalized.mode;

  const structured = waiting && normalized.mode !== 'free_text';
  const freeText = waiting && normalized.mode === 'free_text';
  const signature = revisionInteractionSignature(normalized);
  const expectedButtonCount = structured ? normalized.choices.length : 0;
  const sameInteraction = signature === revisionLastInteractionSignature;
  const stableStructuredDom = (
    structured &&
    sameInteraction &&
    quickRoot.querySelectorAll(':scope > .choice-option-row').length === expectedButtonCount
  );
  const controlsEnabled = waiting && !busy && !locked;

  quickRoot.hidden = !structured;
  composerRoot.hidden = !freeText;

  if (stableStructuredDom) {
    revisionSetStructuredButtonsEnabled(quickRoot, controlsEnabled);
    return;
  }

  revisionHideChoiceTooltip({force: true});
  revisionLastInteractionSignature = signature;
  quickRoot.innerHTML = '';
  quickRoot.className = 'quick-actions';
  if (!structured) return;

  quickRoot.classList.add('structured-options', 'choice-help-options');
  if (normalized.mode === 'yes_no') quickRoot.classList.add('binary-options');
  if (normalized.mode === 'continue') quickRoot.classList.add('continue-options');

  normalized.choices.forEach(choice => {
    const row = document.createElement('div');
    row.className = 'choice-option-row';

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'choice-option-button';
    button.textContent = choice.label;
    if (/^\+\s*Add new/i.test(choice.label)) button.classList.add('add-new-option');
    button.disabled = !controlsEnabled;
    button.addEventListener('click', () =>
      sendValue(String(choice.value ?? ''), choice.label)
    );

    const helpButton = revisionCreateChoiceHelpButton(choice);
    row.append(button, helpButton);
    quickRoot.appendChild(row);
  });
};

if (!window.__mbseChoiceHelpListenersInstalled) {
  window.__mbseChoiceHelpListenersInstalled = true;

  document.addEventListener('pointerdown', event => {
    if (event.target.closest?.('.choice-help-button')) return;
    document.querySelectorAll('.choice-help-button[aria-expanded="true"]')
      .forEach(item => item.setAttribute('aria-expanded', 'false'));
    revisionHideChoiceTooltip({force: true});
  });

  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    document.querySelectorAll('.choice-help-button[aria-expanded="true"]')
      .forEach(item => item.setAttribute('aria-expanded', 'false'));
    revisionHideChoiceTooltip({force: true});
  });

  const chatRoot = document.getElementById('chat');
  if (chatRoot) {
    chatRoot.addEventListener('scroll', () => revisionHideChoiceTooltip({force: true}), {passive: true});
  }
  window.addEventListener('resize', () => revisionHideChoiceTooltip({force: true}));
}
