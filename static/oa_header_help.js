(() => {
  const wrap = document.getElementById('oaInfoWrap');
  const button = document.getElementById('oaInfoButton');
  const popover = document.getElementById('oaInfoPopover');
  if (!wrap || !button || !popover) return;

  let pinned = false;

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
    hide({force: true});
    button.focus();
  });
})();
