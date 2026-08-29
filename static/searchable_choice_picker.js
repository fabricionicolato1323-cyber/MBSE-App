(() => {
  if (typeof renderRevisionInteraction !== 'function') return;

  const baseRenderRevisionInteraction = renderRevisionInteraction;
  const baseSetStructuredButtonsEnabled = revisionSetStructuredButtonsEnabled;
  const SEARCHABLE_CHOICE_MINIMUM = 6;
  const GROUP_ORDER = [
    'Actions',
    'Participants / Context',
    'Goals',
    'Interactions',
    'Communication Means',
    'Create new',
    'Other options'
  ];

  function choiceGroup(choice) {
    const label = String(choice?.label || '').trim();
    const patterns = [
      [/^Action:\s*/i, 'Actions'],
      [/^Participant\s*\/\s*context:\s*/i, 'Participants / Context'],
      [/^Participant:\s*/i, 'Participants / Context'],
      [/^Goal:\s*/i, 'Goals'],
      [/^Interaction:\s*/i, 'Interactions'],
      [/^Communication(?: mean)?:\s*/i, 'Communication Means']
    ];

    if (/^\+\s*Add new/i.test(label)) {
      return {group: 'Create new', displayLabel: label};
    }

    for (const [pattern, group] of patterns) {
      if (pattern.test(label)) {
        return {group, displayLabel: label.replace(pattern, '').trim() || label};
      }
    }
    return {group: 'Other options', displayLabel: label};
  }

  function shouldUseSearchablePicker(choices) {
    if (!Array.isArray(choices) || choices.length < SEARCHABLE_CHOICE_MINIMUM) return false;
    const typed = choices.filter(choice => {
      const group = choiceGroup(choice).group;
      return group !== 'Other options' && group !== 'Create new';
    });
    return typed.length >= 3;
  }

  function closePicker(picker) {
    const toggle = picker?.querySelector('.choice-picker-toggle');
    const menu = picker?.querySelector('.choice-picker-menu');
    if (!toggle || !menu) return;
    menu.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
  }

  function filterPicker(picker, query) {
    const normalizedQuery = String(query || '').trim().toLocaleLowerCase();
    let anyVisible = false;

    picker.querySelectorAll('.choice-picker-group').forEach(group => {
      let groupVisible = false;
      group.querySelectorAll('.choice-picker-option').forEach(row => {
        const matches = !normalizedQuery || row.dataset.search.includes(normalizedQuery);
        row.hidden = !matches;
        if (matches) groupVisible = true;
      });
      group.hidden = !groupVisible;
      if (groupVisible) {
        anyVisible = true;
        if (normalizedQuery) group.open = true;
      }
    });

    const empty = picker.querySelector('.choice-picker-empty');
    if (empty) empty.hidden = anyVisible;
  }

  function buildSearchablePicker(quickRoot, choices, controlsEnabled) {
    const picker = document.createElement('div');
    picker.className = 'hierarchical-choice-picker';

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'choice-picker-toggle';
    toggle.textContent = `Select from ${choices.length} model items`;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.disabled = !controlsEnabled;

    const menu = document.createElement('div');
    menu.className = 'choice-picker-menu';
    menu.hidden = true;

    const searchWrap = document.createElement('div');
    searchWrap.className = 'choice-picker-search-wrap';
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'choice-picker-search';
    search.placeholder = 'Search model items…';
    search.setAttribute('aria-label', 'Search model items');
    search.disabled = !controlsEnabled;
    searchWrap.appendChild(search);

    const groupsRoot = document.createElement('div');
    groupsRoot.className = 'choice-picker-groups';
    const grouped = new Map();
    choices.forEach(choice => {
      const meta = choiceGroup(choice);
      if (!grouped.has(meta.group)) grouped.set(meta.group, []);
      grouped.get(meta.group).push({choice, displayLabel: meta.displayLabel});
    });

    const openByDefault = choices.length < 15;
    GROUP_ORDER.forEach(groupName => {
      const items = grouped.get(groupName);
      if (!items?.length) return;

      const group = document.createElement('details');
      group.className = 'choice-picker-group';
      group.open = openByDefault;

      const summary = document.createElement('summary');
      summary.textContent = `${groupName} (${items.length})`;
      const optionsRoot = document.createElement('div');
      optionsRoot.className = 'choice-picker-group-options';

      items.forEach(({choice, displayLabel}) => {
        const row = document.createElement('div');
        row.className = 'choice-picker-option choice-option-row';
        row.dataset.search = String(choice.label || '').toLocaleLowerCase();

        const optionButton = document.createElement('button');
        optionButton.type = 'button';
        optionButton.className = 'choice-option-button';
        optionButton.textContent = displayLabel;
        optionButton.disabled = !controlsEnabled;
        if (/^\+\s*Add new/i.test(choice.label)) optionButton.classList.add('add-new-option');
        optionButton.addEventListener('click', () => {
          closePicker(picker);
          sendValue(String(choice.value ?? ''), choice.label);
        });

        row.appendChild(optionButton);
        row.appendChild(revisionCreateChoiceHelpButton(choice));
        optionsRoot.appendChild(row);
      });

      group.append(summary, optionsRoot);
      groupsRoot.appendChild(group);
    });

    const empty = document.createElement('div');
    empty.className = 'choice-picker-empty';
    empty.textContent = 'No matching model items.';
    empty.hidden = true;

    search.addEventListener('input', () => filterPicker(picker, search.value));
    toggle.addEventListener('click', event => {
      event.preventDefault();
      const opening = menu.hidden;
      document.querySelectorAll('.hierarchical-choice-picker .choice-picker-menu:not([hidden])')
        .forEach(otherMenu => {
          if (otherMenu !== menu) {
            otherMenu.hidden = true;
            otherMenu.closest('.hierarchical-choice-picker')
              ?.querySelector('.choice-picker-toggle')
              ?.setAttribute('aria-expanded', 'false');
          }
        });
      menu.hidden = !opening;
      toggle.setAttribute('aria-expanded', opening ? 'true' : 'false');
      if (opening) requestAnimationFrame(() => search.focus());
    });

    menu.append(searchWrap, groupsRoot, empty);
    picker.append(toggle, menu);
    quickRoot.appendChild(picker);
  }

  revisionSetStructuredButtonsEnabled = function searchablePickerSetButtonsEnabled(quickRoot, enabled) {
    baseSetStructuredButtonsEnabled(quickRoot, enabled);
    quickRoot.querySelectorAll('.choice-picker-toggle, .choice-picker-search').forEach(element => {
      element.disabled = !enabled;
    });
  };

  renderRevisionInteraction = function searchablePickerRenderInteraction(
    interaction,
    waiting,
    {locked = false} = {}
  ) {
    const normalized = normalizeRevisionInteraction(interaction);
    if (normalized.mode !== 'choice' || !shouldUseSearchablePicker(normalized.choices)) {
      return baseRenderRevisionInteraction(interaction, waiting, {locked});
    }

    const quickRoot = document.getElementById('quickActions');
    const composerRoot = document.getElementById('composer');
    activeInteractionMode = normalized.mode;

    const structured = waiting;
    const signature = revisionInteractionSignature(normalized);
    const sameInteraction = signature === revisionLastInteractionSignature;
    const expectedButtonCount = normalized.choices.length;
    const stablePickerDom = (
      structured &&
      sameInteraction &&
      quickRoot.dataset.choiceRenderer === 'searchable' &&
      quickRoot.querySelectorAll('.choice-option-button').length === expectedButtonCount
    );
    const controlsEnabled = waiting && !busy && !locked;

    quickRoot.hidden = !structured;
    composerRoot.hidden = true;

    if (stablePickerDom) {
      revisionSetStructuredButtonsEnabled(quickRoot, controlsEnabled);
      return;
    }

    revisionHideChoiceTooltip({force: true});
    revisionLastInteractionSignature = signature;
    quickRoot.innerHTML = '';
    quickRoot.className = 'quick-actions structured-options choice-help-options searchable-choice-options';
    quickRoot.dataset.choiceRenderer = 'searchable';
    if (!structured) return;

    buildSearchablePicker(quickRoot, normalized.choices, controlsEnabled);
  };

  if (!window.__mbseSearchablePickerListenersInstalled) {
    window.__mbseSearchablePickerListenersInstalled = true;
    document.addEventListener('pointerdown', event => {
      document.querySelectorAll('.hierarchical-choice-picker').forEach(picker => {
        if (!picker.contains(event.target)) closePicker(picker);
      });
    });
    document.addEventListener('keydown', event => {
      if (event.key !== 'Escape') return;
      document.querySelectorAll('.hierarchical-choice-picker').forEach(closePicker);
    });
  }
})();
