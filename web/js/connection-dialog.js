(() => {
  const dialog = document.querySelector('#connection-dialog');
  if (!dialog) return;

  document.addEventListener('click', (event) => {
    const control = event.target.closest?.('[data-action="open-connection"],[data-action="close-connection"]');
    if (!control) return;
    if (control.dataset.action === 'open-connection') {
      if (!dialog.open) dialog.showModal();
      return;
    }
    if (dialog.open) dialog.close();
  });
})();
