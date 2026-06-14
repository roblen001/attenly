import type { Session, User } from '@supabase/supabase-js';
import {
  AUTH_PROVIDER,
  LOCAL_AUTH_DISPLAY_NAME,
  LOCAL_AUTH_EMAIL,
  LOCAL_AUTH_TOKEN_PREFILL,
  LOCAL_AUTH_USER_ID,
} from './configs';
import { supabase } from './supabase';

export type AuthProvider = 'supabase' | 'local';
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

const LOCAL_SESSION_KEY = 'attenly:local-auth-session';
const listeners = new Set<AuthStateCallback>();

export const authProvider = AUTH_PROVIDER as AuthProvider;
export const isLocalAuthProvider = authProvider === 'local';
export const localAuthTokenPrefill = LOCAL_AUTH_TOKEN_PREFILL;

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

function readLocalSession(): AppSession | null {
  try {
    const raw = window.localStorage.getItem(LOCAL_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AppSession;
    if (!parsed.access_token || !parsed.user?.id) return null;
    return parsed;
  } catch {
    window.localStorage.removeItem(LOCAL_SESSION_KEY);
    return null;
  }
}

function writeLocalSession(token: string): AppSession {
  const session: AppSession = {
    access_token: token,
    refresh_token: '',
    user: {
      id: LOCAL_AUTH_USER_ID,
      email: LOCAL_AUTH_EMAIL,
      user_metadata: {
        provider: 'local',
        display_name: LOCAL_AUTH_DISPLAY_NAME,
      },
      app_metadata: {},
    },
  };
  window.localStorage.setItem(LOCAL_SESSION_KEY, JSON.stringify(session));
  return session;
}

function notifyLocalAuth(event: AuthChangeEvent, session: AppSession | null) {
  listeners.forEach((listener) => listener(event, session));
}

async function getSession(): Promise<AuthResult> {
  if (isLocalAuthProvider) {
    return { data: { session: readLocalSession() }, error: null };
  }

  const result = await requireSupabase().auth.getSession();
  return {
    data: { session: toAppSession(result.data.session) },
    error: result.error,
  };
}

function onAuthStateChange(callback: AuthStateCallback): AuthSubscription {
  if (isLocalAuthProvider) {
    listeners.add(callback);
    window.setTimeout(() => callback('INITIAL_SESSION', readLocalSession()), 0);
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
  if (isLocalAuthProvider) {
    const token = credentials.password.trim();
    if (!token) {
      return { data: { session: null }, error: new Error('Access token is required') };
    }
    const session = writeLocalSession(token);
    notifyLocalAuth('SIGNED_IN', session);
    return { data: { session }, error: null };
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
  if (isLocalAuthProvider) {
    window.localStorage.removeItem(LOCAL_SESSION_KEY);
    notifyLocalAuth('SIGNED_OUT', null);
    return { error: null };
  }

  return requireSupabase().auth.signOut(options);
}

async function signUp(credentials: { email: string; password: string }) {
  if (isLocalAuthProvider) {
    return { data: null, error: new Error('Sign up is not available in local auth mode') };
  }
  return requireSupabase().auth.signUp(credentials);
}

async function resetPasswordForEmail(email: string, options?: { redirectTo?: string }) {
  if (isLocalAuthProvider) {
    return { data: null, error: new Error('Password reset is not available in local auth mode') };
  }
  return requireSupabase().auth.resetPasswordForEmail(email, options);
}

async function updateUser(attributes: { password?: string }) {
  if (isLocalAuthProvider) {
    return { data: null, error: new Error('Password updates are not available in local auth mode') };
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
