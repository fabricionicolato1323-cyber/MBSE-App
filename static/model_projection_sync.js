(() => {
  const renderers = new Map();
  let latestModel = {nodes: [], drafts: [], edges: []};
  let latestSession = '';
  let latestSignature = '';

  function canonicalValue(value) {
    if (Array.isArray(value)) return value.map(canonicalValue);
    if (value && typeof value === 'object') {
      const result = {};
      Object.keys(value).sort().forEach(key => {
        result[key] = canonicalValue(value[key]);
      });
      return result;
    }
    return value;
  }

  function canonicalCollection(items) {
    return (Array.isArray(items) ? items : [])
      .map(item => canonicalValue(item))
      .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
  }

  function signatureForModel(model) {
    return JSON.stringify({
      nodes: canonicalCollection(model?.nodes),
      drafts: canonicalCollection(model?.drafts),
      edges: canonicalCollection(model?.edges),
    });
  }

  function invokeRenderer(name, renderer, model, session, context) {
    try {
      renderer(model, session, context);
    } catch (error) {
      console.error(`Model projection '${name}' failed to refresh.`, error);
    }
  }

  function register(name, renderer) {
    if (!name || typeof renderer !== 'function') return () => {};
    renderers.set(name, renderer);
    if (latestSignature) {
      invokeRenderer(name, renderer, latestModel, latestSession, {
        signature: latestSignature,
        changed: false,
        initial: true,
      });
    }
    return () => renderers.delete(name);
  }

  function apply(model, session = '') {
    const nextModel = model || {nodes: [], drafts: [], edges: []};
    const nextSession = String(session || '');
    const nextSignature = signatureForModel(nextModel);
    const changed = nextSignature !== latestSignature || nextSession !== latestSession;

    latestModel = nextModel;
    latestSession = nextSession;
    if (!changed) return false;
    latestSignature = nextSignature;

    const context = {signature: nextSignature, changed: true, initial: false};
    renderers.forEach((renderer, name) => {
      invokeRenderer(name, renderer, nextModel, nextSession, context);
    });

    window.dispatchEvent(new CustomEvent('mbse:model-projections-updated', {
      detail: {
        model: nextModel,
        session_id: nextSession,
        signature: nextSignature,
      },
    }));
    return true;
  }

  window.mbseModelProjectionSync = Object.freeze({
    register,
    apply,
    signatureForModel,
    getLatest() {
      return {model: latestModel, session_id: latestSession, signature: latestSignature};
    },
  });

  register('pseudo-code', model => {
    if (typeof window.renderRevisionTextualModel === 'function') {
      window.renderRevisionTextualModel(model);
    }
  });
  register('details', model => {
    if (typeof window.renderRevisionDetails === 'function') {
      window.renderRevisionDetails(model);
    }
  });
})();