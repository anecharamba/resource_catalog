import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { API_BASE } from "../../api";

export default function Login() {
  const { login, register, sessionExpired } = useAuth();
  const navigate = useNavigate();
  const [setup, setSetup] = useState(null);
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [setupKey, setSetupKey] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/auth/setup-status`)
      .then(async r => { if (!r.ok) throw new Error("Could not check setup status"); return r.json(); })
      .then(data => { setSetup(data); if (data.setup_required) setMode("register"); })
      .catch(e => setError(e.message));
  }, []);

  const submit = async (e) => {
    e.preventDefault(); setError(null); setBusy(true);
    try {
      if (mode === "login") await login(username, password);
      else await register(username, password, setupKey);
      navigate("/admin");
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  if (!setup) return <div className="admin-auth"><div className="auth-card"><h1>ExamVault Admin</h1><p className="muted">Checking administrator setup…</p></div></div>;

  return (
    <div className="admin-auth">
      <form className="auth-card" onSubmit={submit}>
        <h1>{mode === "login" ? "Admin sign in" : "Initial admin setup"}</h1>
        <p className="muted">{mode === "login" ? "Sign in to manage the paper collection." : "Create the first administrator account. This page closes permanently after setup."}</p>
        {sessionExpired && mode === "login" && <p className="auth-session-notice">Your session ended — sign in again.</p>}
        {setup.setup_required && mode === "login" && <p className="auth-session-notice">No administrator exists yet. Create the first account below.</p>}
        <label className="field"><span>Username</span><input value={username} onChange={e => setUsername(e.target.value)} pattern="[A-Za-z0-9_.-]+" minLength={3} maxLength={50} required /></label>
        <label className="field"><span>Password</span><input type="password" value={password} onChange={e => setPassword(e.target.value)} minLength={10} maxLength={200} required /></label>
        {mode === "register" && setup.setup_key_required && <label className="field"><span>Setup key</span><input type="password" value={setupKey} onChange={e => setSetupKey(e.target.value)} required /></label>}
        {error && <p className="form-error">{error}</p>}
        <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create administrator"}</button>
        {!setup.setup_required && <button type="button" className="link-btn" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>{mode === "login" ? "Initial setup already complete — use sign in" : "Back to sign in"}</button>}
        <Link to="/privacy" className="link auth-privacy-link">Privacy Policy</Link>
      </form>
    </div>
  );
}
