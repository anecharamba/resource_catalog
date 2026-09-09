import { useEffect, useState } from "react";
import { useAuth } from "../../context/AuthContext";
import { apiDelete, apiGet, apiPatch, apiPost } from "../../api";

function formatDate(value) {
  if (!value) return "Never";
  const d = new Date(value.replace(" ", "T") + (value.endsWith("Z") ? "" : "Z"));
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

export default function AdminUsers() {
  const { token, username: currentUsername } = useAuth();
  const [admins, setAdmins] = useState([]);
  const [audit, setAudit] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const [newAdmin, setNewAdmin] = useState({ username: "", password: "" });
  const [ownPassword, setOwnPassword] = useState({ current_password: "", new_password: "" });

  const load = async () => {
    setError(null);
    try {
      const [accounts, activity] = await Promise.all([apiGet("/admin/users", token), apiGet("/admin/users/audit?limit=50", token)]);
      setAdmins(accounts); setAudit(activity);
    }
    catch (e) { setError(e.message); }
  };

  useEffect(() => { load(); }, [token]);

  const createAdmin = async (e) => {
    e.preventDefault(); setBusy(true); setError(null); setMessage(null);
    try {
      await apiPost("/admin/users", newAdmin, token);
      setNewAdmin({ username: "", password: "" });
      setMessage("Administrator created."); await load();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const toggle = async (admin) => {
    setError(null); setMessage(null);
    try {
      await apiPatch(`/admin/users/${admin.id}`, { is_active: !admin.is_active }, token);
      setMessage(`${admin.username} is now ${admin.is_active ? "disabled" : "active"}.`); await load();
    } catch (e) { setError(e.message); }
  };

  const rename = async (admin) => {
    const username = window.prompt("New username", admin.username);
    if (username === null || username.trim() === admin.username) return;
    setError(null); setMessage(null);
    try { await apiPatch(`/admin/users/${admin.id}`, { username: username.trim() }, token); setMessage("Username updated."); await load(); }
    catch (e) { setError(e.message); }
  };

  const resetPassword = async (admin) => {
    const password = window.prompt(`Set a new password for ${admin.username}. Minimum 10 characters.`);
    if (password === null) return;
    setError(null); setMessage(null);
    try { await apiPost(`/admin/users/${admin.id}/reset-password`, { password }, token); setMessage("Password reset successfully."); }
    catch (e) { setError(e.message); }
  };

  const remove = async (admin) => {
    if (!window.confirm(`Delete administrator "${admin.username}"? This cannot be undone.`)) return;
    setError(null); setMessage(null);
    try { await apiDelete(`/admin/users/${admin.id}`, token); setMessage("Administrator deleted."); await load(); }
    catch (e) { setError(e.message); }
  };

  const changeOwnPassword = async (e) => {
    e.preventDefault(); setBusy(true); setError(null); setMessage(null);
    try {
      await apiPost("/admin/me/password", ownPassword, token);
      setOwnPassword({ current_password: "", new_password: "" });
      setMessage("Your password has been changed.");
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <section className="admin-section">
      <div className="section-heading">
        <div><p className="eyebrow">Administration</p><h1>Administrators</h1><p className="muted">Create, disable, rename and remove accounts. Passwords are never displayed.</p></div>
      </div>
      {error && <p className="form-error">{error}</p>}
      {message && <p className="auth-session-notice">{message}</p>}

      <div className="admin-grid-2">
        <form className="panel" onSubmit={createAdmin}>
          <h2>Add administrator</h2>
          <label className="field"><span>Username</span><input value={newAdmin.username} onChange={e => setNewAdmin({ ...newAdmin, username: e.target.value })} pattern="[A-Za-z0-9_.-]+" minLength={3} maxLength={50} required /></label>
          <label className="field"><span>Temporary password</span><input type="password" value={newAdmin.password} onChange={e => setNewAdmin({ ...newAdmin, password: e.target.value })} minLength={10} maxLength={200} required /></label>
          <button className="btn btn-primary" disabled={busy}>{busy ? "Saving…" : "Create administrator"}</button>
        </form>

        <form className="panel" onSubmit={changeOwnPassword}>
          <h2>Change my password</h2>
          <label className="field"><span>Current password</span><input type="password" value={ownPassword.current_password} onChange={e => setOwnPassword({ ...ownPassword, current_password: e.target.value })} required /></label>
          <label className="field"><span>New password</span><input type="password" value={ownPassword.new_password} onChange={e => setOwnPassword({ ...ownPassword, new_password: e.target.value })} minLength={10} maxLength={200} required /></label>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Change password"}</button>
        </form>
      </div>

      <div className="panel admin-users-panel">
        <div className="panel-heading"><h2>Accounts</h2><span className="muted">{admins.length} account{admins.length === 1 ? "" : "s"}</span></div>
        <div className="admin-users-table-wrap">
          <table className="admin-users-table">
            <thead><tr><th>Username</th><th>Status</th><th>Created</th><th>Last login</th><th>Actions</th></tr></thead>
            <tbody>{admins.map(admin => (
              <tr key={admin.id}>
                <td><strong>{admin.username}</strong>{admin.username === currentUsername && <span className="muted"> (you)</span>}</td>
                <td><span className={`status-pill ${admin.is_active ? "status-ok" : "status-muted"}`}>{admin.is_active ? "Active" : "Disabled"}</span></td>
                <td>{formatDate(admin.created_at)}</td>
                <td>{formatDate(admin.last_login_at)}</td>
                <td className="admin-actions">
                  <button className="link-btn" onClick={() => rename(admin)}>Rename</button>
                  <button className="link-btn" onClick={() => resetPassword(admin)}>Reset password</button>
                  {admin.username !== currentUsername && <button className="link-btn" onClick={() => toggle(admin)}>{admin.is_active ? "Disable" : "Enable"}</button>}
                  {admin.username !== currentUsername && <button className="link-btn danger" onClick={() => remove(admin)}>Delete</button>}
                </td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </div>

      <div className="panel admin-users-panel">
        <div className="panel-heading"><h2>Account activity</h2><span className="muted">Latest 50 events</span></div>
        <div className="admin-users-table-wrap">
          <table className="admin-users-table">
            <thead><tr><th>Time</th><th>Action</th><th>Administrator</th><th>Target</th><th>Details</th></tr></thead>
            <tbody>{audit.map(event => (
              <tr key={event.id}>
                <td>{formatDate(event.created_at)}</td>
                <td>{event.action}</td>
                <td>{event.actor_username || "System"}</td>
                <td>{event.target_username || "Deleted account"}</td>
                <td>{event.details && event.details !== "{}" ? event.details : "—"}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
