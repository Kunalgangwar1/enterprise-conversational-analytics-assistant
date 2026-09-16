import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";

import { getCurrentPrincipal } from "../api/auth";
import { ApiError } from "../api/client";
import type { AuthPrincipal, Permission } from "../api/types";

interface AuthContextValue {
  principal: AuthPrincipal;
  hasPermission: (permission: Permission) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [principal, setPrincipal] = useState<AuthPrincipal | null>(null);
  const [status, setStatus] = useState<"loading" | "authenticated" | "unauthenticated" | "error">(
    "loading",
  );

  useEffect(() => {
    const controller = new AbortController();
    void getCurrentPrincipal(controller.signal)
      .then((identity) => {
        setPrincipal(identity);
        setStatus("authenticated");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setStatus(error instanceof ApiError && error.status === 401 ? "unauthenticated" : "error");
      });
    return () => controller.abort();
  }, []);

  const value = useMemo<AuthContextValue | null>(() => {
    if (principal === null) return null;
    const permissions = new Set(principal.permissions);
    return { principal, hasPermission: (permission) => permissions.has(permission) };
  }, [principal]);

  if (status === "loading") {
    return <main className="auth-state" role="status">Loading authentication…</main>;
  }
  if (status === "unauthenticated") {
    return <main className="auth-state"><h1>Authentication required</h1></main>;
  }
  if (status === "error" || value === null) {
    return <main className="auth-state" role="alert">Authentication could not be verified.</main>;
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
