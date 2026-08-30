(() => {
  if (window.__oaDiagramCapabilitiesDefaultInstalled) return;
  window.__oaDiagramCapabilitiesDefaultInstalled = true;

  const LAYOUT_VERSION = 3;
  const storageKeyForSession = session =>
    `oa-diagram-layout:v${LAYOUT_VERSION}:${String(session || '').trim() || 'default'}`;

  function ensureCapabilitiesPreference(session) {
    const key = storageKeyForSession(session);
    let saved = {};
    try {
      saved = JSON.parse(localStorage.getItem(key) || '{}') || {};
    } catch (_error) {
      saved = {};
    }

    if (saved.version !== LAYOUT_VERSION) saved = {version: LAYOUT_VERSION};
    if (typeof saved.showCapabilities === 'boolean') return false;

    saved.showCapabilities = false;
    try { localStorage.setItem(key, JSON.stringify(saved)); }
    catch (_error) { /* local persistence is optional */ }
    return true;
  }

  const baseApplyState = window.applyState;
  if (typeof baseApplyState === 'function') {
    window.applyState = function capabilityDefaultAwareApplyState(state) {
      ensureCapabilitiesPreference(state?.session_id);
      return baseApplyState(state);
    };
  }

  // Cover the already-active session as well. Subsequent sessions are handled
  // by the applyState wrapper above. Existing explicit user preferences are
  // preserved; only missing preferences are initialized to Off.
  try {
    if (typeof activeSessionId !== 'undefined') {
      const seeded = ensureCapabilitiesPreference(activeSessionId);
      if (seeded) window.oaDiagram?.setCapabilitiesVisible?.(false);
    }
  } catch (_error) {
    ensureCapabilitiesPreference('default');
  }
})();
