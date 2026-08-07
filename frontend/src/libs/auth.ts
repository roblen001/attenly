import type { Session, User } from '@supabase/supabase-js';
import {
  API_BASE_URL,
  AUTH_PROVIDER,
  LOCAL_AUTH_DISPLAY_NAME,
  LOCAL_AUTH_EMAIL,
  LOCAL_AUTH_USER_ID,
} from './configs';
import { supabase } from './supabase';

export type AuthProvider = 'supabase' | 'local' | 'external_jwt' | 'oidc';
export type AuthChangeEvent =
  | 'INITIAL_SESSION'
  | 'SIGNED_IN'
  | 'SIGNED_OUT'
  | 'PASSWORD_RECOVERY'
  | 'TOKEN_REFRESHED'
  | 'USER_UPDATED'
  | 'MFA_CHALLENGE_VERIFIED';

export type AppUser = Pick<User, 'id' | 'email' | 'user_metadata'> & {
  app_metadata?: Record<string, unknown>;
};

export type AppSession = Pick<Session, 'access_token' | 'refresh_token'> & {
  user: AppUser;
};

type AuthResult = {
  data: { session: AppSession | null };
  error: Error | null;
};

type AuthSubscription = {
  data: {
    subscription: {
      unsubscribe: () => void;
    };
  };
};

type SignOutOptions = {
  scope?: 'global' | 'local' | 'others';
};

type AuthStateCallback = (event: AuthChangeEvent, session: AppSession | null) => void;

type AuthenticatedUserResponse = {
  id: string;
  email?: string | null;
  user_metadata?: Record<string, unknown> | null;
  app_metadata?: Record<string, unknown> | null;
  display_name?: string | null;
  app_user_id?: string | null;
  organization_id?: string | null;
  organization_role?: string | null;
  organization_status?: string | null;
  role?: string | null;
};

export const authProvider = AUTH_PROVIDER as AuthProvider;
export const isLocalAuthProvider = authProvider === 'local';
export const isTokenAuthProvider = authProvider === 'local' || authProvider === 'external_jwt';
export const isOidcAuthProvider = authProvider === 'oidc';

const TOKEN_SESSION_KEY = authProvider === 'local'
  ? 'attenly:local-auth-session'
  : `attenly:${AUTH_PROVIDER}:auth-session`;
const AUTH_ERROR_KEY = 'attenly:auth-error';
const AUTH_RETURN_TO_KEY = 'attenly:auth-return-to';
const listeners = new Set<AuthStateCallback>();
let oidcSessionCache: AppSession | null | undefined;
let oidcSessionRequest: Promise<AppSession | null> | null = null;

function backendUrl(path: string) {
  return `${API_BASE_URL.replace(/\/$/, '')}${path}`;
}

/**
 * Accept only a path on this application. The backend applies the same check;
 * keeping it here also prevents accidentally constructing an open redirect.
 */
export function safeRelativeReturnPath(candidate?: string | null): string {
  if (!candidate || !candidate.startsWith('/') || candidate.startsWith('//') || candidate.includes('\\')) {
    return '/dashboard';
  }

  try {
    const url = new URL(candidate, window.location.origin);
    if (url.origin !== window.location.origin) return '/dashboard';
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return '/dashboard';
  }
}

export function storeAuthError(message: string) {
  try {
    window.sessionStorage.setItem(AUTH_ERROR_KEY, message);
  } catch {
    // The login page still has a generic fallback when session storage is unavailable.
  }
}

export function consumeAuthError(): string {
  try {
    const message = window.sessionStorage.getItem(AUTH_ERROR_KEY) ?? '';
    window.sessionStorage.removeItem(AUTH_ERROR_KEY);
    return message;
  } catch {
    return '';
  }
}

function requireSupabase() {
  if (!supabase) {
    throw new Error('Supabase auth is not configured');
  }
  return supabase;
}

function toAppSession(session: Session | null): AppSession | null {
  if (!session) return null;
  return {
    access_token: session.access_token,
    refresh_token: session.refresh_token,
    user: {
      id: session.user.id,
      email: session.user.email,
      user_metadata: session.user.user_metadata,
      app_metadata: session.user.app_metadata,
    },
  };
}

export function storeAuthReturnPath(candidate: string): void {
  try {
    window.sessionStorage.setItem(AUTH_RETURN_TO_KEY, safeRelativeReturnPath(candidate));
  } catch {
    // Returning to the dashboard remains a safe fallback when storage is unavailable.
  }
}

export function consumeAuthReturnPath(): string | null {
  try {
    const candidate = window.sessionStorage.getItem(AUTH_RETURN_TO_KEY);
    window.sessionStorage.removeItem(AUTH_RETURN_TO_KEY);
    return candidate ? safeRelativeReturnPath(candidate) : null;
  } catch {
    return null;
  }
}

function toOidcSession(authenticatedUser: AuthenticatedUserResponse): AppSession {
  const displayName = authenticatedUser.display_name
    ?? (typeof authenticatedUser.user_metadata?.display_name === 'string'
      ? authenticatedUser.user_metadata.display_name
      : undefined);

  const organizationRole = authenticatedUser.organization_role ?? authenticatedUser.role;

  return {
    // OIDC provider tokens stay in the backend-for-frontend session. These
    // empty compatibility fields keep consumers focused on session.user.
    access_token: '',
    refresh_token: '',
    user: {
      id: authenticatedUser.id,
      email: authenticatedUser.email ?? undefined,
      user_metadata: {
        provider: 'oidc',
        ...(displayName ? { display_name: displayName } : {}),
        ...(authenticatedUser.user_metadata ?? {}),
      },
      app_metadata: {
        ...(authenticatedUser.app_user_id ? { app_user_id: authenticatedUser.app_user_id } : {}),
        ...(authenticatedUser.organization_id
          ? { organization_id: authenticatedUser.organization_id }
          : {}),
        ...(organizationRole ? { role: organizationRole } : {}),
        ...(authenticatedUser.organization_status
          ? { organization_status: authenticatedUser.organization_status }
          : {}),
        ...(authenticatedUser.app_metadata ?? {}),
      },
    },
  };
}

function decodeJwtPayload(token: string): Record<string, unknown> {
  try {
    const payload = token.split('.')[1];
    if (!payload) return {};
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
    return JSON.parse(window.atob(padded));
  } catch {
    return {};
  }
}

function readTokenSession(): AppSession | null {
  try {
    const raw = window.localStorage.getItem(TOKEN_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AppSession;
    if (!parsed.access_token || !parsed.user?.id) return null;
    return parsed;
  } catch {
    window.localStorage.removeItem(TOKEN_SESSION_KEY);
    return null;
  }
}

function writeTokenSession(token: string, authenticatedUser: AuthenticatedUserResponse): AppSession {
  const jwtClaims = authProvider === 'external_jwt' ? decodeJwtPayload(token) : {};
  const userId = authenticatedUser.id || (typeof jwtClaims.sub === 'string' ? jwtClaims.sub : LOCAL_AUTH_USER_ID);
  const email = authenticatedUser.email || (typeof jwtClaims.email === 'string' ? jwtClaims.email : LOCAL_AUTH_EMAIL);
  const displayName = typeof jwtClaims.name === 'string' ? jwtClaims.name : LOCAL_AUTH_DISPLAY_NAME;

  const session: AppSession = {
    access_token: token,
    refresh_token: '',
    user: {
      id: userId,
      email,
      user_metadata: {
        provider: authProvider,
        display_name: displayName,
        ...(authenticatedUser.user_metadata ?? {}),
      },
      app_metadata: {},
    },
  };
  window.localStorage.setItem(TOKEN_SESSION_KEY, JSON.stringify(session));
  return session;
}

async function validateTokenWithBackend(token: string): Promise<AuthenticatedUserResponse> {
  const tokenName = isLocalAuthProvider ? 'deployment access token' : 'identity token';

  let response: Response;
  try {
    response = await fetch(backendUrl('/auth/api/auth/me'), {
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      },
    });
  } catch {
    throw new Error('Unable to verify the access token. Check that Attenly is running and try again.');
  }

  if (!response.ok) {
    let detail = '';
    try {
      const body = await response.json() as { detail?: unknown };
      detail = typeof body.detail === 'string' ? body.detail : '';
    } catch {
      // Use the status-specific message below when the response is not JSON.
    }

    if (response.status === 401 || response.status === 403) {
      throw new Error(`That ${tokenName} is invalid. Enter a current token and try again.`);
    }

    throw new Error(detail || `Unable to verify the access token (server returned ${response.status}).`);
  }

  const user = await response.json() as AuthenticatedUserResponse;
  if (!user.id) {
    throw new Error('The authentication server returned an invalid user identity.');
  }
  return user;
}

async function requestOidcSession(): Promise<AppSession | null> {
  let response: Response;
  try {
    response = await fetch(backendUrl('/auth/api/auth/me'), {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    });
  } catch {
    throw new Error('Unable to check your company session. Check that Attenly is running and try again.');
  }

  if (response.status === 401) {
    oidcSessionCache = null;
    return null;
  }

  if (!response.ok) {
    let detail = '';
    try {
      const body = await response.json() as { detail?: unknown };
      detail = typeof body.detail === 'string' ? body.detail : '';
    } catch {
      // Use the status-specific fallback below when the response is not JSON.
    }
    throw new Error(detail || `Unable to check your company session (server returned ${response.status}).`);
  }

  const authenticatedUser = await response.json() as AuthenticatedUserResponse;
  if (!authenticatedUser.id) {
    throw new Error('The authentication server returned an invalid user identity.');
  }

  oidcSessionCache = toOidcSession(authenticatedUser);
  return oidcSessionCache;
}

async function readOidcSession(): Promise<AppSession | null> {
  if (oidcSessionCache !== undefined) return oidcSessionCache;
  if (oidcSessionRequest) return oidcSessionRequest;

  oidcSessionRequest = requestOidcSession();
  try {
    return await oidcSessionRequest;
  } finally {
    oidcSessionRequest = null;
  }
}

function notifyTokenAuth(event: AuthChangeEvent, session: AppSession | null) {
  listeners.forEach((listener) => listener(event, session));
}

async function getSession(): Promise<AuthResult> {
  if (isTokenAuthProvider) {
    return { data: { session: readTokenSession() }, error: null };
  }

  if (isOidcAuthProvider) {
    try {
      return { data: { session: await readOidcSession() }, error: null };
    } catch (error) {
      return {
        data: { session: null },
        error: error instanceof Error ? error : new Error('Unable to check your company session.'),
      };
    }
  }

  const result = await requireSupabase().auth.getSession();
  return {
    data: { session: toAppSession(result.data.session) },
    error: result.error,
  };
}

function onAuthStateChange(callback: AuthStateCallback): AuthSubscription {
  if (isTokenAuthProvider || isOidcAuthProvider) {
    listeners.add(callback);
    window.setTimeout(() => {
      if (isTokenAuthProvider) {
        callback('INITIAL_SESSION', readTokenSession());
        return;
      }

      void getSession().then(({ data }) => callback('INITIAL_SESSION', data.session));
    }, 0);
    return {
      data: {
        subscription: {
          unsubscribe: () => {
            listeners.delete(callback);
          },
        },
      },
    };
  }

  const { data } = requireSupabase().auth.onAuthStateChange((event, session) => {
    callback(event as AuthChangeEvent, toAppSession(session));
  });
  return { data };
}

async function signInWithPassword(credentials: { email: string; password: string }) {
  if (isTokenAuthProvider) {
    const token = credentials.password.trim();
    if (!token) {
      return { data: { session: null }, error: new Error('Access token is required') };
    }

    try {
      const authenticatedUser = await validateTokenWithBackend(token);
      const session = writeTokenSession(token, authenticatedUser);
      notifyTokenAuth('SIGNED_IN', session);
      return { data: { session }, error: null };
    } catch (error) {
      return {
        data: { session: null },
        error: error instanceof Error ? error : new Error('Unable to verify the access token.'),
      };
    }
  }

  if (isOidcAuthProvider) {
    return { data: { session: null }, error: new Error('Use company SSO to sign in') };
  }

  const result = await requireSupabase().auth.signInWithPassword(credentials);
  return {
    data: { session: toAppSession(result.data.session) },
    error: result.error,
  };
}

async function signInWithToken(token: string) {
  return signInWithPassword({ email: LOCAL_AUTH_EMAIL, password: token });
}

async function signInWithOidc(returnTo = '/dashboard') {
  if (!isOidcAuthProvider) {
    return { data: { session: null }, error: new Error('Company SSO is not configured') };
  }

  const loginUrl = new URL(backendUrl('/auth/oidc/login'), window.location.origin);
  loginUrl.searchParams.set('return_to', safeRelativeReturnPath(returnTo));
  window.location.assign(loginUrl.toString());
  return { data: { session: null }, error: null };
}

async function signOut(options?: SignOutOptions) {
  if (isTokenAuthProvider) {
    window.localStorage.removeItem(TOKEN_SESSION_KEY);
    notifyTokenAuth('SIGNED_OUT', null);
    return { error: null };
  }

  if (isOidcAuthProvider) {
    let response: Response;
    try {
      response = await fetch(backendUrl('/auth/oidc/logout'), {
        method: 'POST',
        credentials: 'include',
        headers: { Accept: 'application/json' },
      });
    } catch {
      return { error: new Error('Unable to sign out. Check that Attenly is running and try again.') };
    }

    if (!response.ok && response.status !== 401) {
      return { error: new Error(`Unable to sign out (server returned ${response.status}).`) };
    }

    oidcSessionCache = null;
    notifyTokenAuth('SIGNED_OUT', null);
    return { error: null };
  }

  return requireSupabase().auth.signOut(options);
}

async function signUp(credentials: { email: string; password: string }) {
  if (isTokenAuthProvider || isOidcAuthProvider) {
    return { data: null, error: new Error('Sign up is not available for this authentication provider') };
  }
  return requireSupabase().auth.signUp(credentials);
}

async function resetPasswordForEmail(email: string, options?: { redirectTo?: string }) {
  if (isTokenAuthProvider || isOidcAuthProvider) {
    return { data: null, error: new Error('Password reset is not available for this authentication provider') };
  }
  return requireSupabase().auth.resetPasswordForEmail(email, options);
}

async function updateUser(attributes: { password?: string }) {
  if (isTokenAuthProvider || isOidcAuthProvider) {
    return { data: null, error: new Error('Password updates are not available for this authentication provider') };
  }
  return requireSupabase().auth.updateUser(attributes);
}

export const authClient = {
  getSession,
  onAuthStateChange,
  signInWithPassword,
  signInWithToken,
  signInWithOidc,
  signOut,
  signUp,
  resetPasswordForEmail,
  updateUser,
};
