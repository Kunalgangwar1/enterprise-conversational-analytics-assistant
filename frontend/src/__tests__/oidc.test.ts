import type { User } from "oidc-client-ts";

import {
  buildOidcSettings,
  getOidcAccessToken,
  initializeOidcAuthentication,
  logoutFromOidc,
} from "../auth/oidc";

function setOidcGlobals(): void {
  (globalThis as typeof globalThis & { __AUTH_MODE__: string }).__AUTH_MODE__ = "oidc";
  (globalThis as typeof globalThis & { __OIDC_AUTHORITY__: string }).__OIDC_AUTHORITY__ =
    "https://issuer.example.invalid/pool";
  (globalThis as typeof globalThis & { __OIDC_CLIENT_ID__: string }).__OIDC_CLIENT_ID__ =
    "synthetic-client";
  (globalThis as typeof globalThis & { __OIDC_REDIRECT_URI__: string }).__OIDC_REDIRECT_URI__ =
    "https://app.example.invalid/";
  (globalThis as typeof globalThis & { __OIDC_POST_LOGOUT_REDIRECT_URI__: string })
    .__OIDC_POST_LOGOUT_REDIRECT_URI__ = "https://app.example.invalid/";
  (globalThis as typeof globalThis & { __OIDC_MANAGED_LOGIN_DOMAIN__: string })
    .__OIDC_MANAGED_LOGIN_DOMAIN__ = "https://login.example.invalid";
}

function syntheticUser(): User {
  return {
    access_token: "synthetic-access-token",
    expired: false,
  } as User;
}

describe("OIDC authorization-code integration", () => {
  beforeEach(() => {
    setOidcGlobals();
    localStorage.clear();
    sessionStorage.clear();
    window.history.replaceState({}, "", "/#/dashboard");
  });

  test("configures authorization code with PKCE and an in-memory user store", async () => {
    const settings = buildOidcSettings();

    expect(settings.response_type).toBe("code");
    expect(settings.disablePKCE).toBe(false);
    expect(settings.client_secret).toBeUndefined();
    await settings.userStore?.set("user", JSON.stringify(syntheticUser()));
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.getItem("access_token")).toBeNull();
    expect(sessionStorage.getItem("refresh_token")).toBeNull();
  });

  test("processes a callback and removes code and state from browser history", async () => {
    window.history.replaceState({}, "", "/?code=synthetic-code&state=synthetic-state#/dashboard");
    const oidcManager = {
      getUser: jest.fn(),
      removeUser: jest.fn(),
      signinRedirect: jest.fn(),
      signinRedirectCallback: jest.fn().mockResolvedValue(syntheticUser()),
      signoutRedirect: jest.fn(),
    };

    await initializeOidcAuthentication(oidcManager);

    expect(oidcManager.signinRedirectCallback).toHaveBeenCalledWith(
      expect.stringContaining("code=synthetic-code"),
    );
    expect(getOidcAccessToken()).toBe("synthetic-access-token");
    expect(window.location.search).toBe("");
    expect(window.location.hash).toBe("#/dashboard");
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.getItem("access_token")).toBeNull();
    expect(sessionStorage.getItem("refresh_token")).toBeNull();
  });

  test("logout removes the in-memory user before provider redirect", async () => {
    const calls: string[] = [];
    let logoutUrl = "";
    const oidcManager = {
      getUser: jest.fn(),
      signinRedirect: jest.fn(),
      signinRedirectCallback: jest.fn(),
      removeUser: jest.fn(async () => { calls.push("remove"); }),
      signoutRedirect: jest.fn(),
    };

    await logoutFromOidc(oidcManager, (url) => {
      logoutUrl = url;
      calls.push("redirect");
    });

    expect(calls).toEqual(["remove", "redirect"]);
    expect(logoutUrl).toContain("/logout?");
    expect(logoutUrl).toContain("client_id=synthetic-client");
    expect(logoutUrl).toContain("logout_uri=https%3A%2F%2Fapp.example.invalid%2F");
    expect(getOidcAccessToken()).toBeUndefined();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.getItem("access_token")).toBeNull();
  });
});
