import { useState } from "react";
import { useAuth } from "../auth.jsx";

export default function LoginPage() {
  const { login, defaultPasswords } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState("");
  const [needCode, setNeedCode] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await login(username.trim(), password, needCode ? code.trim() : undefined);
      if (res === "mfa") {
        setNeedCode(true);
        setBusy(false);
      }
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <img src="/shield.svg" alt="" className="login-logo" />
        <h1>CyberShield SecOps</h1>
        <p className="muted small">Security operations center for satellite-5G IoT · sign in</p>
        <label>
          <span>Username</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required />
        </label>
        <label>
          <span>Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 autoComplete="current-password" required />
        </label>
        {needCode && (
          <label>
            <span>Two-factor code (authenticator app)</span>
            <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code"
                   pattern="[0-9 ]{6,7}" maxLength={7} autoFocus required placeholder="123456" />
          </label>
        )}
        {error && <div className="config-error">{error}</div>}
        <button className="btn btn-primary login-btn" disabled={busy}>{busy ? "Signing in…" : needCode ? "Verify code" : "Sign in"}</button>
        {defaultPasswords && <details className="muted small login-help">
          <summary>First start? Default accounts</summary>
          <p><b>Platform (provider, sees every company):</b> admin / Admin@2026 · operator / Operator@2026 · viewer / Viewer@2026.</p>
          <p><b>SOC team (platform):</b> analyst_l1 / AnalystL1@2026 (triage) · analyst_l2 / AnalystL2@2026 (investigate,
            request containment) · analyst_l3 / AnalystL3@2026 (respond, approve) · soc_manager / Manager@2026.</p>
          <p><b>Demo companies (see only their own devices):</b> farm_admin / Farm@2026 (Atlas Dairy Farms) ·
            offices_admin / Offices@2026 (Casa Business Center) · solar_admin / Solar@2026 (Sahara Solar) ·
            mining_admin / Mining@2026 (Atlas Mining Corp) · hospital_admin / Hospital@2026 (Medina Health Hospital) ·
            logistics_admin / Logistics@2026 (Tangier Cold Chain Logistics).</p>
          <p>Change these passwords after the first login (Account menu, top right).</p>
        </details>}
        <div className="powered">Built on Huawei Cloud: ECS · RDS · IoTDA · ModelArts · AI by DeepSeek</div>
      </form>
    </div>
  );
}
