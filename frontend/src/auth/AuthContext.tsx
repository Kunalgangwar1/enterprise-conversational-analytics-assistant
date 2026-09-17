import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";

import { getCurrentPrincipal } from "../api/auth";
import { ApiError, setAccessTokenProvider } from "../api/client";
import type { AuthPrincipal, Permission } from "../api/types";
import {
  beginOidcLogin,
  getOidcAccessToken,
  initializeOidcAuthentication,
  logoutFromOidc,
  oidcAuthenticationEnabled,
} from "./oidc";

interface AuthContextValue {
  principal: AuthPrincipal;
  hasPermission: (permission: Permission) => boolean;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [principal, setPrincipal] = useState<AuthPrincipal | null>(null);
  const [status, setStatus] = useState<"loading" | "authenticated" | "unauthenticated" | "error">(
    "loading",
  );

  useEffect(() => {
    const controller = new AbortController();
    const initialize = async () => {
      if (oidcAuthenticationEnabled()) {
        await initializeOidcAuthentication();
        setAccessTokenProvider(getOidcAccessToken);
      } else {
        setAccessTokenProvider(() => undefined);
      }
      return getCurrentPrincipal(controller.signal);
    };
    void initialize()
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
    return {
      principal,
      hasPermission: (permission) => permissions.has(permission),
      logout: async () => {
        setPrincipal(null);
        setAccessTokenProvider(() => undefined);
        if (oidcAuthenticationEnabled()) await logoutFromOidc();
        else setStatus("unauthenticated");
      },
    };
  }, [principal]);

  if (status === "loading") {
    return <main className="auth-state" role="status">Loading authentication…</main>;
  }
  if (status === "unauthenticated") {
    return (
      <main className="auth-state">
        <div>
          <h1>Authentication required</h1>
          {oidcAuthenticationEnabled() && (
            <button className="primary-button" type="button" onClick={() => void beginOidcLogin()}>
              Sign in
            </button>
          )}
        </div>
      </main>
    );
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
