import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { apiLogin, apiMe, apiRegister, type UserPublic } from "../lib/api";
import { clearAccessToken, getAccessToken, setAccessToken } from "../lib/token";

type AuthContextValue = {
  user: UserPublic | null;
  email: string | null;
  paid: boolean;
  isAdmin: boolean;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<UserPublic>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const applySession = useCallback((next: UserPublic, token: string) => {
    setAccessToken(token);
    setUser(next);
    setError(null);
  }, []);

  const refreshUser = useCallback(async () => {
    const token = getAccessToken();
    if (!token) {
      setUser(null);
      return;
    }
    const me = await apiMe();
    setUser(me);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (!getAccessToken()) {
          return;
        }
        const me = await apiMe();
        if (!cancelled) setUser(me);
      } catch {
        clearAccessToken();
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      setError(null);
      const data = await apiLogin(email, password);
      applySession(data.user, data.access_token);
      return data.user;
    },
    [applySession],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      setError(null);
      const data = await apiRegister(email, password);
      applySession(data.user, data.access_token);
    },
    [applySession],
  );

  const logout = useCallback(() => {
    clearAccessToken();
    setUser(null);
    setError(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      email: user?.email ?? null,
      paid: user?.paid ?? false,
      isAdmin: user?.role === "admin",
      loading,
      error,
      login,
      register,
      logout,
      refreshUser,
    }),
    [user, loading, error, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
