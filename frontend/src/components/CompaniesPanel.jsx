import { useEffect, useState } from "react";
import { api } from "../services/api.js";

const EMPTY = { company_id: "", name: "", sector: "farm", admin_username: "", admin_password: "" };
const SECTORS = ["farm", "offices", "energy", "factory", "hospital", "school", "logistics", "other"];
const slug = (text) => text.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);

// v1.2 (platform admin): the customer companies, their devices, and new companies.
// Each company only sees its own devices; the satellite, ground station, 5G tower,
// core and security server are shared by everyone.
export default function CompaniesPanel() {
  const [data, setData] = useState({ companies: [], platform_devices: [] });
  const [form, setForm] = useState(EMPTY);
  const [msg, setMsg] = useState(null);

  const load = () => api.companies().then(setData).catch((e) => setMsg({ ok: false, text: e.message }));
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
    const body = { ...form, company_id: form.company_id || slug(form.name) };
    if (!body.admin_username) {
      delete body.admin_username;
      delete body.admin_password;
    }
    if (await run(api.createCompany(body), `Company ${form.name} created.`)) setForm(EMPTY);
  }

  const allDevices = [...data.companies.flatMap((c) => c.devices.map((d) => [d, c.company_id])),
    ...data.platform_devices.map((d) => [d, ""])].sort();

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Companies</h2>
      </div>

      <div className="company-list">
        {data.companies.map((c) => (
          <div key={c.company_id} className="company-card">
            <h3>{c.name} <span className="muted small">({c.company_id}{c.sector ? ` · ${c.sector}` : ""})</span></h3>
            <div className="small">Users: {c.users.length ? c.users.join(", ") : <span className="muted">none yet</span>}</div>
            <div className="company-devices">
              {c.devices.length ? c.devices.map((d) => <span key={d} className="company-chip">{d}</span>)
                : <span className="muted small">no devices yet</span>}
            </div>
            {!c.users.length && !c.devices.length && (
              <div className="assign-row">
                <button className="btn btn-small btn-danger" onClick={() => window.confirm(`Delete ${c.name}?`) && run(api.deleteCompany(c.company_id), `${c.name} deleted.`)}>
                  Delete company</button>
              </div>
            )}
          </div>
        ))}
        {data.platform_devices.length > 0 && (
          <div className="company-card">
            <h3>Platform</h3>
            <div className="company-devices">{data.platform_devices.map((d) => <span key={d} className="company-chip">{d}</span>)}</div>
          </div>
        )}
      </div>

      <h3 className="small muted">Which company owns each device</h3>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Device</th><th>Company</th></tr></thead>
          <tbody>
            {allDevices.map(([d, owner]) => (
              <tr key={d}>
                <td><b>{d}</b></td>
                <td>
                  <select value={owner} onChange={(e) => run(api.assignDevice(d, e.target.value), `${d} now belongs to ${e.target.value || "the platform"}.`)}>
                    <option value="">platform (no company)</option>
                    {data.companies.map((c) => <option key={c.company_id} value={c.company_id}>{c.name}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <form className="config-form user-form" onSubmit={create}>
        <h3>Add a company</h3>
        <div className="builder-row three">
          <label><span>Name</span>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required minLength={2} placeholder="Green Valley Farm" /></label>
          <label><span>Short ID (letters, digits, -)</span>
            <input value={form.company_id} onChange={(e) => setForm({ ...form, company_id: e.target.value.toLowerCase() })}
                   pattern="[a-z0-9][a-z0-9-]*" minLength={3} maxLength={40} placeholder={slug(form.name) || "green-valley"} /></label>
          <label><span>Sector</span>
            <select value={form.sector} onChange={(e) => setForm({ ...form, sector: e.target.value })}>
              {SECTORS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select></label>
          <label><span>First admin username (optional)</span>
            <input value={form.admin_username} onChange={(e) => setForm({ ...form, admin_username: e.target.value })} placeholder="greenvalley_admin" /></label>
          <label><span>First admin password</span>
            <input type="password" value={form.admin_password} onChange={(e) => setForm({ ...form, admin_password: e.target.value })}
                   required={!!form.admin_username} /></label>
        </div>
        <div className="config-actions"><button className="btn btn-small btn-primary">Add company</button></div>
      </form>
      {msg && <div className={`small ${msg.ok ? "tone-ok" : "tone-bad"}`}>{msg.text}</div>}
    </section>
  );
}
