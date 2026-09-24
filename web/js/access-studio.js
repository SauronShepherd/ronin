import { del, get, put } from './api.js';
import { json } from './dom.js';

async function loadAccess() {
  if (location.hash.slice(1) !== 'access') return;
  const view = document.querySelector('#view'); if (!view || document.querySelector('#access-inventory')) return;
  const panel = document.createElement('section'); panel.id = 'access-inventory'; panel.className = 'panel';
  panel.innerHTML = `<h2>Access administration</h2>
    <form id="role-binding-form" class="toolbar">
      <label>Subject kind<select id="role-subject-kind" class="field"><option value="principal">principal</option><option value="group">group</option></select></label>
      <label>Subject ID<input id="role-subject-id" class="field" required></label>
      <label>Role<select id="role-name" class="field" required><option value="viewer">viewer</option><option value="editor">editor</option><option value="operator">operator</option><option value="admin">admin</option></select></label>
      <button class="button primary" type="submit">Assign role</button>
      <button class="button" type="button" id="remove-role-binding">Remove role</button>
    </form>
    <form id="group-membership-form" class="toolbar">
      <label>Group ID<input id="membership-group-id" class="field" required></label>
      <label>Principal ID<input id="membership-principal-id" class="field" required></label>
      <button class="button primary" type="submit">Add member</button>
      <button class="button" type="button" id="remove-group-member">Remove member</button>
      <button class="button" type="button" id="list-group-members">List members</button>
    </form>
    <form id="group-form" class="toolbar">
      <label>Group ID<input id="group-id" class="field" required></label>
      <label>Group name<input id="group-name" class="field" required></label>
      <button class="button primary" type="submit">Create/update group</button>
    </form>
    <form id="service-identity-form" class="toolbar">
      <label>Service ID<input id="service-id" class="field" required></label>
      <label>Display name<input id="service-display-name" class="field" required></label>
      <label>Issuer<input id="service-issuer" class="field" value="ronin" required></label>
      <label>Subject<input id="service-subject" class="field" required></label>
      <button class="button primary" type="submit">Create/enable service</button>
      <button class="button" type="button" id="disable-service">Disable service</button>
      <button class="button" type="button" id="rotate-service">Rotate service</button>
    </form>
    <form id="user-principal-form" class="toolbar">
      <label>User ID<input id="user-id" class="field" required></label>
      <label>Display name<input id="user-display-name" class="field" required></label>
      <label>Issuer<input id="user-issuer" class="field" value="oidc" required></label>
      <label>Subject<input id="user-subject" class="field" required></label>
      <label>Email<input id="user-email" class="field" type="email"></label>
      <button class="button primary" type="submit">Create/update user</button>
    </form>
    <h3>Workspace scope</h3>
    <table class="data-table" id="access-scope-table"><thead><tr><th>Workspace</th><th>Subject</th><th>Role</th></tr></thead><tbody><tr><td colspan="3">Loading…</td></tr></tbody></table>
    <pre class="code" id="access-inventory-output" aria-live="polite">Loading security state…</pre>`; view.append(panel);
  const refreshInventory = async () => {
    const output = panel.querySelector('#access-inventory-output');
    const rows = panel.querySelector('#access-scope-table tbody');
    const [principals, groups, bindings] = await Promise.all([
      get('/v1/admin/security/principals'), get('/v1/admin/security/groups'), get('/v1/admin/security/role-bindings'),
    ]);
    output.textContent = json({ principals, groups, bindings });
    rows.replaceChildren(...(bindings.items || []).map((binding) => {
      const row = document.createElement('tr');
      for (const value of [binding.workspace_id, `${binding.subject_kind}:${binding.subject_id}`, binding.role]) {
        const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
      }
      return row;
    }));
    if (!rows.children.length) rows.innerHTML = '<tr><td colspan="3">No role bindings</td></tr>';
  };
  panel.querySelector('#role-binding-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const output = panel.querySelector('#access-inventory-output');
    const kind = panel.querySelector('#role-subject-kind').value;
    const subject = encodeURIComponent(panel.querySelector('#role-subject-id').value.trim());
    const role = encodeURIComponent(panel.querySelector('#role-name').value.trim());
    try {
      const binding = await put(`/v1/admin/security/role-bindings/${kind}/${subject}/${role}`, {});
      output.textContent = json(binding);
      await refreshInventory();
    } catch (error) { output.textContent = `Role assignment failed: ${error.message}`; }
  });
  panel.querySelector('#remove-role-binding').addEventListener('click', async () => {
    const output = panel.querySelector('#access-inventory-output');
    const kind = panel.querySelector('#role-subject-kind').value;
    const subject = encodeURIComponent(panel.querySelector('#role-subject-id').value.trim());
    const role = encodeURIComponent(panel.querySelector('#role-name').value.trim());
    try {
      const result = await del(`/v1/admin/security/role-bindings/${kind}/${subject}/${role}`);
      output.textContent = json(result);
      await refreshInventory();
    } catch (error) { output.textContent = `Role removal failed: ${error.message}`; }
  });
  const membershipPath = () => `/v1/admin/security/groups/${encodeURIComponent(panel.querySelector('#membership-group-id').value.trim())}/members/${encodeURIComponent(panel.querySelector('#membership-principal-id').value.trim())}`;
  panel.querySelector('#group-membership-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const output = panel.querySelector('#access-inventory-output');
    try { output.textContent = json(await put(membershipPath(), {})); await refreshInventory(); }
    catch (error) { output.textContent = `Member add failed: ${error.message}`; }
  });
  panel.querySelector('#remove-group-member').addEventListener('click', async () => {
    const output = panel.querySelector('#access-inventory-output');
    try { output.textContent = json(await del(membershipPath())); await refreshInventory(); }
    catch (error) { output.textContent = `Member removal failed: ${error.message}`; }
  });
  panel.querySelector('#list-group-members').addEventListener('click', async () => {
    const output = panel.querySelector('#access-inventory-output');
    const group = encodeURIComponent(panel.querySelector('#membership-group-id').value.trim());
    try { output.textContent = json(await get(`/v1/admin/security/groups/${group}/members`)); }
    catch (error) { output.textContent = `Member listing failed: ${error.message}`; }
  });
  panel.querySelector('#group-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const output = panel.querySelector('#access-inventory-output');
    const id = encodeURIComponent(panel.querySelector('#group-id').value.trim());
    const name = panel.querySelector('#group-name').value.trim();
    try { output.textContent = json(await put(`/v1/admin/security/groups/${id}`, { name })); await refreshInventory(); }
    catch (error) { output.textContent = `Group update failed: ${error.message}`; }
  });
  panel.querySelector('#user-principal-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const output = panel.querySelector('#access-inventory-output');
    const id = panel.querySelector('#user-id').value.trim();
    try {
      output.textContent = json(await put(`/v1/admin/security/principals/${encodeURIComponent(id)}`, {
        kind: 'user', display_name: panel.querySelector('#user-display-name').value.trim(),
        issuer: panel.querySelector('#user-issuer').value.trim(), subject: panel.querySelector('#user-subject').value.trim(),
        email: panel.querySelector('#user-email').value.trim() || null, active: true,
      }));
      await refreshInventory();
    } catch (error) { output.textContent = `User principal update failed: ${error.message}`; }
  });
  const servicePayload = (id, active = true) => ({
    kind: 'service',
    display_name: panel.querySelector('#service-display-name').value.trim(),
    issuer: panel.querySelector('#service-issuer').value.trim(),
    subject: panel.querySelector('#service-subject').value.trim(),
    active,
  });
  const servicePath = () => `/v1/admin/security/principals/${encodeURIComponent(panel.querySelector('#service-id').value.trim())}`;
  panel.querySelector('#service-identity-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const output = panel.querySelector('#access-inventory-output');
    try { output.textContent = json(await put(servicePath(), servicePayload(panel.querySelector('#service-id').value.trim()))); await refreshInventory(); }
    catch (error) { output.textContent = `Service identity update failed: ${error.message}`; }
  });
  panel.querySelector('#disable-service').addEventListener('click', async () => {
    const output = panel.querySelector('#access-inventory-output');
    try { output.textContent = json(await put(servicePath(), servicePayload(panel.querySelector('#service-id').value.trim(), false))); await refreshInventory(); }
    catch (error) { output.textContent = `Service identity disable failed: ${error.message}`; }
  });
  panel.querySelector('#rotate-service').addEventListener('click', async () => {
    const output = panel.querySelector('#access-inventory-output');
    const replacement = window.prompt('Replacement service ID');
    if (!replacement?.trim()) return;
    try {
      const created = await put(`/v1/admin/security/principals/${encodeURIComponent(replacement.trim())}`, servicePayload(replacement.trim()));
      const disabled = await put(servicePath(), servicePayload(panel.querySelector('#service-id').value.trim(), false));
      output.textContent = json({ replacement: created, disabled });
      await refreshInventory();
    } catch (error) { output.textContent = `Service identity rotation failed: ${error.message}`; }
  });
  try {
    await refreshInventory();
  } catch (error) { panel.querySelector('#access-inventory-output').textContent = `Access inventory failed: ${error.message}`; }
}

setTimeout(() => { window.addEventListener('hashchange', () => setTimeout(loadAccess, 0)); loadAccess(); }, 0);
