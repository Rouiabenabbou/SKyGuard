import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, LOGGED_OUT_EVENT, setToken } from "./services/api.js";

// v1.1: who is logged in, and what their role allows. v1.2: and which company they belong to.
// Roles: viewer (read only) < operator (respond to incidents) < admin (everything).
// v2.1: SOC roles L1 / L2 / L3 / manager sit at the operator level; what they may change is set by
// their permissions (sent by the backend, which checks them again on every request).
const RANK = { viewer: 1, soc_l1: 2, soc_l2: 2, soc_l3: 2, soc_manager: 2, operator: 2, admin: 3 };
const ALL_PERMS = ["read", "triage", "hunt", "incident", "intel", "simulate", "contain_request", "contain", "contain_approve",
  "playbook", "respond", "rules", "admin"];
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [state, setState] = useState({ loading: true, user: null, authEnabled: true, defaultPasswords: false });

  const refresh = useCallback(async () => {
    try {
      const cfg = await api.authConfig();
      if (!cfg.auth_enabled) {
        setState({ loading: false, user: { username: "guest", role: "admin", permissions: ALL_PERMS }, authEnabled: false });
        return;
      }
      const defaultPasswords = cfg.default_passwords;
      setState((s) => ({ ...s, defaultPasswords }));
      if (!getToken()) {  // not signed in yet: show the login page without a failed call
        setState({ loading: false, user: null, authEnabled: true, defaultPasswords });
        return;
      }
      const me = await api.me();
      setState({ loading: false, user: me.user, authEnabled: true, defaultPasswords });
    } catch {
      setState((s) => ({ ...s, loading: false, user: null }));
    }
  }, []);

  useEffect(() => {
    refresh();
    const onLoggedOut = () => setState((s) => (s.authEnabled ? { ...s, user: null } : s));
    window.addEventListener(LOGGED_OUT_EVENT, onLoggedOut);
    return () => window.removeEventListener(LOGGED_OUT_EVENT, onLoggedOut);
  }, [refresh]);

  // Lets CSS hide buttons the role can't use (.need-operator, .need-admin)
  // and, v1.2, shared-network buttons a company user can't use (.need-platform).
  useEffect(() => {
    document.documentElement.dataset.role = state.user?.role ?? "none";
    const perms = state.user?.permissions ?? [];
    document.documentElement.dataset.noperm = ALL_PERMS.filter((p) => !perms.includes(p)).join(" ");
    document.documentElement.dataset.scope = state.user?.company_id ? "company" : "platform";
  }, [state.user]);

  // Returns "mfa" when the account has two-factor login on and no code was given yet.
  const login = async (username, password, code) => {
    const res = await api.login(username, password, code);
    if (res.mfa_required) return "mfa";
    setToken(res.token);
    setState((s) => ({ ...s, loading: false, user: res.user, authEnabled: true }));
  };

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      /* already logged out */
    }
    setToken(null);
    setState((s) => ({ ...s, user: null }));
  };

  const can = (role) => !!state.user && RANK[state.user.role] >= RANK[role];
  const has = (perm) => !!state.user && (state.user.permissions ?? []).includes(perm);
  // v1.2: platform users (the provider) have no company and see every company.
  const company = state.user?.company_id ? { id: state.user.company_id, name: state.user.company_name } : null;
  const isPlatform = !company;

  return (
    <AuthContext.Provider value={{ ...state, login, logout, can, has, refresh, company, isPlatform }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
