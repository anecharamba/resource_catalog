import { NavLink, Navigate, Outlet, Link } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../context/ThemeContext";

const NAV_ITEMS = [
  { to: "/admin", label: "Dashboard", end: true },
  { to: "/admin/import", label: "Import" },
  { to: "/admin/review", label: "Review queue" },
  { to: "/admin/catalog", label: "Catalog" },
  { to: "/admin/users", label: "Administrators" },
];

export default function AdminLayout() {
  const { isAuthed, username, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  if (!isAuthed) return <Navigate to="/admin/login" replace />;

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <Link to="/" className="admin-brand">ExamVault <span className="muted">Admin</span></Link>
        <nav>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `admin-nav-link${isActive ? " active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="admin-sidebar-footer">
          <button className="icon-btn" onClick={toggleTheme} title="Toggle dark mode">
            {theme === "dark" ? "☀" : "☾"}
          </button>
          <div className="admin-user">
            <span>{username}</span>
            <button className="link-btn" onClick={logout}>Sign out</button>
          </div>
        </div>
      </aside>
      <main className="admin-main">
        <Outlet />
      </main>
    </div>
  );
}
