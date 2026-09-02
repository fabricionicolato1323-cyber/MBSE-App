(() => {
  const wrap = document.getElementById('oaInfoWrap');
  const button = document.getElementById('oaInfoButton');
  const legacyPopover = document.getElementById('oaInfoPopover');
  if (!wrap || !button || !legacyPopover) return;

  const popover = document.createElement('div');
  popover.id = legacyPopover.id;
  popover.className = legacyPopover.className;
  popover.hidden = true;
  popover.setAttribute('role', 'dialog');
  popover.setAttribute('aria-modal', 'false');
  popover.setAttribute('aria-label', 'Operational Analysis help');
  legacyPopover.replaceWith(popover);

  let pinned = false;

  function element(tag, className = '', text = '') {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function renderPath(path) {
    if (!Array.isArray(path) || !path.length) return null;
    const container = element('div', 'oa-help-path');
    path.forEach((step, index) => {
      if (!step || typeof step !== 'object') return;
      const card = element('div', 'oa-help-path-step');
      const number = element('span', 'oa-help-path-number', String(index + 1));
      const copy = element('span', 'oa-help-path-copy');
      copy.append(
        element('strong', '', String(step.label || '')),
        element('span', '', String(step.description || '')),
      );
      card.append(number, copy);
      container.appendChild(card);
    });
    return container.childElementCount ? container : null;
  }

  function renderSection(section) {
    if (!section || typeof section !== 'object') return null;
    const block = element('section', 'oa-help-section');
    const title = String(section.title || '').trim();
    const body = String(section.body || '').trim();
    const items = Array.isArray(section.items) ? section.items : [];

    if (title) block.appendChild(element('h3', '', title));
    if (body) block.appendChild(element('p', '', body));

    if (items.length) {
      const list = element('ul', 'oa-help-list');
      items.forEach(item => {
        const text = String(item || '').trim();
        if (text) list.appendChild(element('li', '', text));
      });
      if (list.childElementCount) block.appendChild(list);
    }

    const path = renderPath(section.path);
    if (path) block.appendChild(path);

    return block.childElementCount ? block : null;
  }

  function renderHelp(data) {
    popover.replaceChildren();
    const help = data && typeof data === 'object' ? data : {};
    const summary = help.summary && typeof help.summary === 'object' ? help.summary : {};

    const ariaLabel = String(help.aria_label || '').trim();
    if (ariaLabel) popover.setAttribute('aria-label', ariaLabel);

    const intro = element('div', 'oa-help-intro');
    const eyebrow = String(summary.eyebrow || '').trim();
    const title = String(summary.title || '').trim();
    const body = String(summary.body || '').trim();
    if (eyebrow) intro.appendChild(element('div', 'oa-help-eyebrow', eyebrow));
    if (title) intro.appendChild(element('h2', '', title));
    if (body) intro.appendChild(element('p', '', body));
    if (intro.childElementCount) popover.appendChild(intro);

    const focusSteps = Array.isArray(help.focus_steps) ? help.focus_steps : [];
    if (focusSteps.length) {
      const focus = element('div', 'oa-help-focus');
      const focusLabel = String(help.focus_label || '').trim();
      if (focusLabel) focus.appendChild(element('strong', 'oa-help-focus-label', focusLabel));
      const flow = element('div', 'oa-help-focus-flow');
      focusSteps.forEach(step => {
        const text = String(step || '').trim();
        if (!text) return;
        if (flow.childElementCount) flow.appendChild(element('span', 'oa-help-focus-arrow', '→'));
        flow.appendChild(element('span', 'oa-help-focus-step', text));
      });
      if (flow.childElementCount) focus.appendChild(flow);
      popover.appendChild(focus);
    }

    const sections = Array.isArray(help.sections) ? help.sections : [];
    if (sections.length) {
      const details = element('details', 'oa-help-details');
      const detailsSummary = element(
        'summary',
        '',
        String(help.details_label || 'Learn more about this viewpoint'),
      );
      details.appendChild(detailsSummary);
      const content = element('div', 'oa-help-details-content');
      sections.forEach(section => {
        const rendered = renderSection(section);
        if (rendered) content.appendChild(rendered);
      });
      details.appendChild(content);
      popover.appendChild(details);
    }

    const sources = Array.isArray(help.sources) ? help.sources : [];
    const sourceNote = String(help.source_note || '').trim();
    if (sourceNote || sources.length) {
      const footer = element('footer', 'oa-help-sources');
      if (sourceNote) footer.appendChild(element('span', 'oa-help-source-note', sourceNote));
      if (sources.length) {
        const links = element('div', 'oa-help-source-links');
        sources.forEach(source => {
          if (!source || typeof source !== 'object') return;
          const label = String(source.label || '').trim();
          const url = String(source.url || '').trim();
          if (!label || !url) return;
          const link = element('a', '', label);
          link.href = url;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          links.appendChild(link);
        });
        if (links.childElementCount) footer.appendChild(links);
      }
      popover.appendChild(footer);
    }

    if (!popover.childElementCount) {
      popover.appendChild(element('p', 'oa-help-unavailable', 'Help content is unavailable.'));
    }
  }

  async function loadHelp() {
    try {
      const response = await fetch('/api/ui-guidance/oa-help', {cache: 'no-store'});
      if (!response.ok) throw new Error(`Help request failed: ${response.status}`);
      renderHelp(await response.json());
    } catch (_error) {
      renderHelp({});
    }
  }

  function show() {
    popover.hidden = false;
    button.setAttribute('aria-expanded', 'true');
  }

  function hide({force = false} = {}) {
    if (pinned && !force) return;
    popover.hidden = true;
    button.setAttribute('aria-expanded', 'false');
  }

  wrap.addEventListener('mouseenter', show);
  wrap.addEventListener('mouseleave', () => hide());
  wrap.addEventListener('focusin', show);
  wrap.addEventListener('focusout', event => {
    if (!wrap.contains(event.relatedTarget)) hide();
  });

  button.addEventListener('click', event => {
    event.preventDefault();
    event.stopPropagation();
    pinned = !pinned;
    if (pinned) show();
    else hide({force: true});
  });

  document.addEventListener('pointerdown', event => {
    if (wrap.contains(event.target)) return;
    pinned = false;
    hide({force: true});
  });

  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    pinned = false;
    button.focus();
    hide({force: true});
  });

  loadHelp();
})();
