import { createContext, useCallback, useEffect, useState, type ReactNode } from "react";
import { getMe } from "../api/auth";
import { clearToken, getToken, setToken, UNAUTHORIZED_EVENT } from "../api/client";
import type { User } from "../api/types";

interface AuthState {
  token: string | null;
  user: User | null;
  loading: boolean;
}

export interface AuthContextValue extends AuthState {
  login: (token: string, user: User) => void;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: getToken(),
    user: null,
    loading: !!getToken(),
  });

  useEffect(() => {
    let cancelled = false;
    const token = getToken();
    if (!token) {
      setState({ token: null, user: null, loading: false });
      return;
    }
    getMe()
      .then((user) => {
        if (cancelled) return;
        setState({ token, user, loading: false });
      })
      .catch(() => {
        if (cancelled) return;
        clearToken();
        setState({ token: null, user: null, loading: false });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function onUnauthorized() {
      setState({ token: null, user: null, loading: false });
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const login = useCallback((token: string, user: User) => {
    setToken(token);
    setState({ token, user, loading: false });
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setState({ token: null, user: null, loading: false });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
