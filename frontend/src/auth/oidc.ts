import {
  InMemoryWebStorage,
  type User,
  UserManager,
  type UserManagerSettings,
  WebStorageStateStore,
} from "oidc-client-ts";

interface OidcManager {
  getUser: () => Promise<User | null>;
  removeUser: () => Promise<void>;
  signinRedirect: () => Promise<void>;
  signinRedirectCallback: (url?: string) => Promise<User>;
  signoutRedirect: () => Promise<void>;
}

let manager: UserManager | null = null;
let accessToken: string | undefined;

export function oidcAuthenticationEnabled(): boolean {
  return __AUTH_MODE__ === "oidc";
}

export function buildOidcSettings(): UserManagerSettings {
  if (!__OIDC_AUTHORITY__ || !__OIDC_CLIENT_ID__ || !__OIDC_REDIRECT_URI__) {
    throw new Error("OIDC frontend configuration is incomplete");
  }
  return {
    authority: __OIDC_AUTHORITY__,
    client_id: __OIDC_CLIENT_ID__,
    redirect_uri: __OIDC_REDIRECT_URI__,
    post_logout_redirect_uri: __OIDC_POST_LOGOUT_REDIRECT_URI__,
    response_type: "code",
    scope: "openid email profile",
    automaticSilentRenew: false,
    monitorSession: false,
    disablePKCE: false,
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    stateStore: new WebStorageStateStore({
      store: window.sessionStorage,
      prefix: "eca_oidc_state:",
    }),
  };
}

function getManager(): UserManager {
  manager ??= new UserManager(buildOidcSettings());
  return manager;
}

export function hasAuthorizationCallback(url = window.location.href): boolean {
  const parameters = new URL(url).searchParams;
  return parameters.has("state") && (parameters.has("code") || parameters.has("error"));
}

export function cleanAuthorizationCallbackUrl(): void {
  const url = new URL(window.location.href);
  for (const parameter of ["code", "state", "session_state", "error", "error_description"]) {
    url.searchParams.delete(parameter);
  }
  const search = url.searchParams.toString();
  const cleanUrl = `${url.pathname}${search ? `?${search}` : ""}${url.hash || "#/"}`;
  window.history.replaceState({}, document.title, cleanUrl);
}

export async function initializeOidcAuthentication(
  oidcManager: OidcManager = getManager(),
): Promise<void> {
  let user: User | null;
  if (hasAuthorizationCallback()) {
    try {
      user = await oidcManager.signinRedirectCallback(window.location.href);
    } finally {
      cleanAuthorizationCallbackUrl();
    }
  } else {
    user = await oidcManager.getUser();
  }
  accessToken = user && !user.expired ? user.access_token : undefined;
}

export function getOidcAccessToken(): string | undefined {
  return accessToken;
}

export async function beginOidcLogin(oidcManager: OidcManager = getManager()): Promise<void> {
  await oidcManager.signinRedirect();
}

export async function logoutFromOidc(
  oidcManager: OidcManager = getManager(),
  navigate: (url: string) => void = (url) => window.location.assign(url),
): Promise<void> {
  accessToken = undefined;
  await oidcManager.removeUser();
  if (__OIDC_MANAGED_LOGIN_DOMAIN__) {
    const logoutUrl = new URL("/logout", __OIDC_MANAGED_LOGIN_DOMAIN__);
    logoutUrl.searchParams.set("client_id", __OIDC_CLIENT_ID__);
    logoutUrl.searchParams.set("logout_uri", __OIDC_POST_LOGOUT_REDIRECT_URI__);
    navigate(logoutUrl.toString());
    return;
  }
  await oidcManager.signoutRedirect();
}
