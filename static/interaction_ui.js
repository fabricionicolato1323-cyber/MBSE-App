(() => {
  const quickActions = document.getElementById('quickActions');
  const composer = document.getElementById('composer');
  const input = document.getElementById('messageInput');

  if (!quickActions || !composer) return;

  quickActions.setAttribute('aria-label', 'Answer options');
  quickActions.setAttribute('role', 'group');

  function syncInteractionControls() {
    const buttons = [...quickActions.querySelectorAll('button')];
    const hasStructuredOptions = buttons.length > 0;

    quickActions.hidden = !hasStructuredOptions;
    composer.hidden = hasStructuredOptions;
    quickActions.classList.toggle('structured-options', hasStructuredOptions);

    const labels = buttons.map(button => button.textContent.trim().toLowerCase());
    const isBinary =
      buttons.length === 2 &&
      labels.includes('yes') &&
      labels.includes('no');
    const isContinue = buttons.length === 1 && labels[0] === 'continue';

    quickActions.classList.toggle('binary-options', isBinary);
    quickActions.classList.toggle('continue-options', isContinue);

    if (!hasStructuredOptions && input && !input.disabled) {
      input.setAttribute('aria-label', 'Answer');
    }
  }

  const observer = new MutationObserver(syncInteractionControls);
  observer.observe(quickActions, {childList: true, subtree: true});
  syncInteractionControls();
})();
