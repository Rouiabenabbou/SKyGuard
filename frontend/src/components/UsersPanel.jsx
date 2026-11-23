import { useEffect, useState } from "react";
import { api } from "../services/api.js";
import { useAuth } from "../auth.jsx";

const ROLES = [["viewer", "viewer"], ["soc_l1", "SOC L1 (triage)"], ["soc_l2", "SOC L2 (investigate)"], ["soc_l3", "SOC L3 (respond)"],
  ["soc_manager", "SOC manager"], ["operator", "operator"], ["admin", "admin"]];
const timeOf = (iso) => (iso ? new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleString() : "never");

// Admin: create users, change their role, lock them out, reset passwords.
// v1.2: a company admin manages only their company's users; the platform admin picks the company.
export default function UsersPanel() {
  const { user: me, isPlatform, company } = useAuth();
  const [users, setUsers] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [form, setForm] = useState({ username: "", password: "", role: "operator", company_id: "" });
  const [msg, setMsg] = useState(null);

  const load = () => {
    api.users().then((r) => setUsers(r.users)).catch((e) => setMsg({ ok: false, text: e.message }));
    if (isPlatform) api.companies().then((r) => setCompanies(r.companies)).catch(() => {});
  };
  useEffect(() => {
    load();
  }, []);

  async function run(promise, ok) {
    try {
      await promise;
      setMsg({ ok: true, text: ok });
      load();
      return true;
    } catch (e) {
      setMsg({ ok: false, text: e.message });
      return false;
    }
  }

  async function create(e) {
    e.preventDefault();
    const body = { ...form, company_id: isPlatform ? form.company_id || null : undefined };
    if (await run(api.createUser(body), `User ${form.username} created.`)) setForm({ ...form, username: "", password: "" });
  }

  function resetPassword(name) {
    const pw = window.prompt(`New password for ${name} (8+ characters, letters and a number):`);
    if (pw) run(api.updateUser(name, { password: pw }), `Password of ${name} changed; they were logged out.`);
  }

  return (
    <section className="panel">
      <div className="panel-head"><h2>Users and roles</h2>
        <span className="muted small">
          {company ? company.name : "All companies"}</span></div>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>User</th>{isPlatform && <th>Company</th>}<th>Role</th><th>Status</th><th>2FA</th><th>Last login</th><th></th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.username}>
                <td><b>{u.username}</b>{u.username === me?.username && <span className="muted small"> (you)</span>}</td>
                {isPlatform && <td className="small">{u.company_name ?? <span className="muted">platform</span>}</td>}
                <td>
                  <select value={u.role} onChange={(e) => run(api.updateUser(u.username, { role: e.target.value }), `${u.username} is now ${e.target.value}.`)}>
                    {ROLES.map(([r, l]) => <option key={r} value={r}>{l}</option>)}
                  </select>
                </td>
                <td className={u.active ? "tone-ok" : "tone-bad"}>{u.active ? "active" : "locked"}</td>
                <td className="small">{u.mfa_enabled ? <span className="tone-ok">on</span> : <span className={u.mfa_required ? "tone-bad" : "muted"}>{u.mfa_required ? "required" : "off"}</span>}</td>
                <td className="small muted">{timeOf(u.last_login)}</td>
                <td className="row-actions">
                  <button className="btn btn-small" onClick={() => resetPassword(u.username)}>Reset password</button>
                  {u.mfa_enabled && <button className="btn btn-small" title="Lost phone: the user sets two-factor up again"
                                            onClick={() => window.confirm(`Reset two-factor login of ${u.username}?`) && run(api.mfaReset(u.username), `Two-factor of ${u.username} reset.`)}>Reset 2FA</button>}
                  <button className="btn btn-small" onClick={() => run(api.updateUser(u.username, { active: !u.active }), `${u.username} ${u.active ? "locked" : "unlocked"}.`)}>
                    {u.active ? "Lock" : "Unlock"}</button>
                  {u.username !== me?.username && (
                    <button className="btn btn-small btn-danger" onClick={() => window.confirm(`Delete ${u.username}?`) && run(api.deleteUser(u.username), `${u.username} deleted.`)}>Delete</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form className="config-form user-form" onSubmit={create}>
        <h3>Add a user</h3>
        <div className="builder-row three">
          <label><span>Username</span><input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required minLength={3} /></label>
          <label><span>Password</span><input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required /></label>
          <label><span>Role</span>
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {ROLES.map(([r, l]) => <option key={r} value={r}>{l}</option>)}
            </select></label>
          {isPlatform && (
            <label><span>Company</span>
              <select value={form.company_id} onChange={(e) => setForm({ ...form, company_id: e.target.value })}>
                <option value="">platform (sees every company)</option>
                {companies.map((c) => <option key={c.company_id} value={c.company_id}>{c.name}</option>)}
              </select></label>
          )}
        </div>
        <div className="config-actions"><button className="btn btn-small btn-primary">Add user</button></div>
      </form>
      {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}
    </section>
  );
}
