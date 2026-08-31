(() => {
  if (window.__mbseSysmlSyntaxHighlightInstalled) return;
  window.__mbseSysmlSyntaxHighlightInstalled = true;

  const KEYWORDS = new Set([
    'package', 'library', 'private', 'public', 'protected', 'import', 'alias',
    'part', 'action', 'item', 'port', 'attribute', 'connection', 'flow',
    'requirement', 'constraint', 'allocation', 'interface', 'occurrence',
    'individual', 'variation', 'variant', 'subject', 'actor', 'use', 'case',
    'view', 'viewpoint', 'rendering', 'analysis', 'metadata', 'comment',
    'ref', 'in', 'out', 'inout', 'of', 'from', 'to', 'first', 'then',
    'connect', 'allocate', 'satisfy', 'verify', 'include', 'expose', 'bind',
    'specializes', 'redefines', 'subsets', 'ordered', 'unique', 'abstract',
    'enum', 'datatype', 'calc', 'def', 'usage', 'perform', 'succession',
  ]);

  const DEFINITIONS = new Set([
    'OperationalEntity', 'OperationalActor', 'OperationalActivity',
    'OperationalInformation', 'OperationalExchange', 'CommunicationMean',
    'OperationalScenario', 'OperationalCapability',
  ]);

  const BUILTIN_TYPES = new Set([
    'String', 'Boolean', 'Integer', 'Real', 'Natural', 'Rational',
  ]);

  let applying = false;
  let scheduled = false;

  function installStyles() {
    if (document.querySelector('link[data-mbse-sysml-syntax]')) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/sysml_syntax_highlight.css';
    link.dataset.mbseSysmlSyntax = 'true';
    document.head.appendChild(link);
  }

  function token(className, text) {
    const span = document.createElement('span');
    span.className = `sysml-token sysml-token-${className}`;
    span.textContent = text;
    return span;
  }

  function appendPlain(parent, text) {
    if (text) parent.appendChild(document.createTextNode(text));
  }

  function classifyWord(word) {
    if (KEYWORDS.has(word)) return 'keyword';
    if (DEFINITIONS.has(word)) return 'definition';
    if (BUILTIN_TYPES.has(word)) return 'type';
    if (/^[A-Z][A-Za-z0-9_]*Definition$/.test(word)) return 'type';
    if (/^[A-Z][A-Za-z0-9_]*Usage$/.test(word)) return 'type';
    return '';
  }

  function highlightLineElement(lineElement) {
    const source = String(lineElement.textContent || '');
    lineElement.textContent = '';
    let index = 0;

    while (index < source.length) {
      if (source.startsWith('//', index)) {
        lineElement.appendChild(token('comment', source.slice(index)));
        break;
      }

      const char = source[index];
      if (char === '"' || char === "'") {
        const quote = char;
        let end = index + 1;
        let escaped = false;
        while (end < source.length) {
          const current = source[end];
          if (!escaped && current === quote) {
            end += 1;
            break;
          }
          if (!escaped && current === '\\') escaped = true;
          else escaped = false;
          end += 1;
        }
        lineElement.appendChild(token('string', source.slice(index, end)));
        index = end;
        continue;
      }

      if (char === '@') {
        const match = source.slice(index).match(/^@[A-Za-z_][A-Za-z0-9_]*/);
        if (match) {
          lineElement.appendChild(token('annotation', match[0]));
          index += match[0].length;
          continue;
        }
      }

      const number = source.slice(index).match(/^[+-]?(?:\d+\.\d+|\d+)(?:[eE][+-]?\d+)?/);
      if (number) {
        lineElement.appendChild(token('number', number[0]));
        index += number[0].length;
        continue;
      }

      const word = source.slice(index).match(/^[A-Za-z_][A-Za-z0-9_]*/);
      if (word) {
        const kind = classifyWord(word[0]);
        if (kind) lineElement.appendChild(token(kind, word[0]));
        else appendPlain(lineElement, word[0]);
        index += word[0].length;
        continue;
      }

      const operator = source.slice(index).match(/^(::|->|=>|:=|\.\.|[{}()[\]:;,.=+*<>|&!?-])/);
      if (operator) {
        lineElement.appendChild(token('operator', operator[0]));
        index += operator[0].length;
        continue;
      }

      appendPlain(lineElement, char);
      index += 1;
    }
  }

  function normaliseLines(code) {
    const existingImpactLines = Array.from(code.children).filter(
      child => child.classList?.contains('mbse-change-line')
    );
    if (existingImpactLines.length) return existingImpactLines;

    const existingSyntaxLines = Array.from(code.children).filter(
      child => child.classList?.contains('sysml-syntax-line')
    );
    if (existingSyntaxLines.length) return existingSyntaxLines;

    const text = String(code.textContent || '');
    code.textContent = '';
    const lines = text.split('\n');
    lines.forEach((line, index) => {
      const row = document.createElement('span');
      row.className = 'sysml-syntax-line';
      row.textContent = line || ' ';
      code.appendChild(row);
      if (index < lines.length - 1) code.appendChild(document.createTextNode('\n'));
    });
    return Array.from(code.querySelectorAll(':scope > .sysml-syntax-line'));
  }

  function apply() {
    scheduled = false;
    if (applying) return;
    const code = document.querySelector('#utilitySysmlView code');
    if (!code) return;

    const currentText = String(code.textContent || '');
    const hasTokens = Boolean(code.querySelector('.sysml-token'));
    if (code.dataset.sysmlSyntaxSource === currentText && hasTokens) return;

    applying = true;
    try {
      const lines = normaliseLines(code);
      lines.forEach(highlightLineElement);
      code.dataset.sysmlSyntaxSource = String(code.textContent || '');
    } finally {
      applying = false;
    }
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(apply);
  }

  installStyles();
  window.mbseSysmlSyntaxHighlight = {apply: schedule};

  window.addEventListener('mbse:model-projections-updated', schedule);
  const root = document.getElementById('utilitySysmlView');
  if (root) {
    const observer = new MutationObserver(() => {
      if (!applying) schedule();
    });
    observer.observe(root, {childList: true, subtree: true, characterData: true});
  }

  schedule();
})();
