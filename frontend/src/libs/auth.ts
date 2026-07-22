import type { Session, User } from '@supabase/supabase-js';
import {
  API_BASE_URL,
  AUTH_PROVIDER,
  LOCAL_AUTH_DISPLAY_NAME,
  LOCAL_AUTH_EMAIL,
  LOCAL_AUTH_USER_ID,
} from './configs';
import { supabase } from './supabase';

export type AuthProvider = 'supabase' | 'local' | 'external_jwt';
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
};

export const authProvider = AUTH_PROVIDER as AuthProvider;
export const isLocalAuthProvider = authProvider === 'local';
export const isTokenAuthProvider = authProvider === 'local' || authProvider === 'external_jwt';

const TOKEN_SESSION_KEY = authProvider === 'local'
  ? 'attenly:local-auth-session'
  : `attenly:${AUTH_PROVIDER}:auth-session`;
const AUTH_ERROR_KEY = 'attenly:auth-error';
const listeners = new Set<AuthStateCallback>();

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
  const apiBaseUrl = API_BASE_URL.replace(/\/$/, '');
  const tokenName = isLocalAuthProvider ? 'deployment access token' : 'identity token';

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/auth/api/auth/me`, {
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

function notifyTokenAuth(event: AuthChangeEvent, session: AppSession | null) {
  listeners.forEach((listener) => listener(event, session));
}

async function getSession(): Promise<AuthResult> {
  if (isTokenAuthProvider) {
    return { data: { session: readTokenSession() }, error: null };
  }

  const result = await requireSupabase().auth.getSession();
  return {
    data: { session: toAppSession(result.data.session) },
    error: result.error,
  };
}

function onAuthStateChange(callback: AuthStateCallback): AuthSubscription {
  if (isTokenAuthProvider) {
    listeners.add(callback);
    window.setTimeout(() => callback('INITIAL_SESSION', readTokenSession()), 0);
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

  const result = await requireSupabase().auth.signInWithPassword(credentials);
  return {
    data: { session: toAppSession(result.data.session) },
    error: result.error,
  };
}

async function signInWithToken(token: string) {
  return signInWithPassword({ email: LOCAL_AUTH_EMAIL, password: token });
}

async function signOut(options?: SignOutOptions) {
  if (isTokenAuthProvider) {
    window.localStorage.removeItem(TOKEN_SESSION_KEY);
    notifyTokenAuth('SIGNED_OUT', null);
    return { error: null };
  }

  return requireSupabase().auth.signOut(options);
}

async function signUp(credentials: { email: string; password: string }) {
  if (isTokenAuthProvider) {
    return { data: null, error: new Error('Sign up is not available in token auth mode') };
  }
  return requireSupabase().auth.signUp(credentials);
}

async function resetPasswordForEmail(email: string, options?: { redirectTo?: string }) {
  if (isTokenAuthProvider) {
    return { data: null, error: new Error('Password reset is not available in token auth mode') };
  }
  return requireSupabase().auth.resetPasswordForEmail(email, options);
}

async function updateUser(attributes: { password?: string }) {
  if (isTokenAuthProvider) {
    return { data: null, error: new Error('Password updates are not available in token auth mode') };
  }
  return requireSupabase().auth.updateUser(attributes);
}

export const authClient = {
  getSession,
  onAuthStateChange,
  signInWithPassword,
  signInWithToken,
  signOut,
  signUp,
  resetPasswordForEmail,
  updateUser,
};
