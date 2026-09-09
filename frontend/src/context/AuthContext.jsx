import { createContext, useContext, useState, useCallback, useEffect } from "react";
import { API_BASE, setUnauthorizedHandler } from "../api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => window.localStorage?.getItem?.("admin_token") || null);
  const [username, setUsername] = useState(() => window.localStorage?.getItem?.("admin_username") || null);
  const [role, setRole] = useState(() => window.localStorage?.getItem?.("admin_role") || null);
  const [sessionExpired, setSessionExpired] = useState(false);

  const logout = useCallback(() => {
    setToken(null);
    setUsername(null);
    setRole(null);
    window.localStorage.removeItem("admin_token");
    window.localStorage.removeItem("admin_username");
    window.localStorage.removeItem("admin_role");
  }, []);

  // If any API call anywhere gets a 401 (expired token, or a token from a
  // database that's since been reset), force a clean logout instead of
  // leaving pages stuck retrying against a session that will never work.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setSessionExpired(true);
      logout();
    });
  }, [logout]);

  const login = useCallback(async (u, p) => {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u, password: p }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Login failed");
    }
    const data = await res.json();
    setSessionExpired(false);
    setToken(data.access_token);
    setUsername(data.username);
    setRole(data.role);
    window.localStorage.setItem("admin_token", data.access_token);
    window.localStorage.setItem("admin_username", data.username);
    window.localStorage.setItem("admin_role", data.role);
    return data;
  }, []);

  const register = useCallback(async (u, p, setupKey) => {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u, password: p, setup_key: setupKey || undefined }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Registration failed");
    }
    const data = await res.json();
    setSessionExpired(false);
    setToken(data.access_token);
    setUsername(data.username);
    setRole(data.role);
    window.localStorage.setItem("admin_token", data.access_token);
    window.localStorage.setItem("admin_username", data.username);
    window.localStorage.setItem("admin_role", data.role);
    return data;
  }, []);

  return (
    <AuthContext.Provider value={{ token, username, role, login, register, logout, isAuthed: !!token, sessionExpired }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
