const labelText = (control) => {
  const name = control.getAttribute('name') || control.id || control.getAttribute('type') || 'field';
  return name.replace(/[-_]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
};

function labelUnlabeledControls(root = document) {
  root.querySelectorAll('.migration-flow').forEach((flow) => {
    flow.setAttribute('tabindex', '0');
    flow.setAttribute('aria-label', 'Migration execution graph');
  });
  root.querySelectorAll('input, select, textarea').forEach((control) => {
    if (control.hasAttribute('aria-label') || control.hasAttribute('aria-labelledby')) return;
    const id = control.id;
    if (id && root.querySelector(`label[for="${CSS.escape(id)}"]`)) return;
    if (control.closest('label')) return;
    control.setAttribute('aria-label', labelText(control));
  });
}

labelUnlabeledControls();
new MutationObserver((mutations) => {
  mutations.forEach((mutation) => mutation.addedNodes.forEach((node) => {
    if (node.nodeType === Node.ELEMENT_NODE) labelUnlabeledControls(node);
  }));
}).observe(document.body, { childList: true, subtree: true });
