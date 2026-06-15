type RuntimeConfigKey =
  | 'VITE_API_BASE_URL'
  | 'VITE_AUTH_PROVIDER'
  | 'VITE_SUPABASE_URL'
  | 'VITE_SUPABASE_ANON_KEY'
  | 'VITE_LOCAL_AUTH_USER_ID'
  | 'VITE_LOCAL_AUTH_EMAIL'
  | 'VITE_LOCAL_AUTH_DISPLAY_NAME'
  | 'VITE_LOCAL_AUTH_TOKEN';

type RuntimeConfig = Partial<Record<RuntimeConfigKey, string>>;

declare global {
  interface Window {
    __ATTENLY_CONFIG__?: RuntimeConfig;
  }
}

function configValue(key: RuntimeConfigKey, fallback = '') {
  return window.__ATTENLY_CONFIG__?.[key] ?? import.meta.env[key] ?? fallback;
}

function isAllowedProductionApiUrl(value: string) {
  if (!value || value.startsWith('/') || value.startsWith('https://')) {
    return true;
  }

  try {
    const url = new URL(value);
    return url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  } catch {
    return false;
  }
}

export const API_BASE_URL = configValue('VITE_API_BASE_URL', 'http://127.0.0.1:8000')
export const AUTH_PROVIDER = configValue('VITE_AUTH_PROVIDER', 'supabase').toLowerCase()
export const SUPABASE_URL = configValue('VITE_SUPABASE_URL')
export const SUPABASE_ANON_KEY = configValue('VITE_SUPABASE_ANON_KEY')
export const LOCAL_AUTH_USER_ID = configValue('VITE_LOCAL_AUTH_USER_ID', 'local-admin')
export const LOCAL_AUTH_EMAIL = configValue('VITE_LOCAL_AUTH_EMAIL', 'local-admin@example.com')
export const LOCAL_AUTH_DISPLAY_NAME = configValue('VITE_LOCAL_AUTH_DISPLAY_NAME', 'Local Admin')
export const LOCAL_AUTH_TOKEN_PREFILL = configValue('VITE_LOCAL_AUTH_TOKEN')

// Production safety check
if (import.meta.env.PROD && !isAllowedProductionApiUrl(API_BASE_URL)) {
  throw new Error('Production VITE_API_BASE_URL must use HTTPS, a same-origin path, or localhost HTTP')
}

// Validate required environment variables
if (AUTH_PROVIDER === 'supabase' && (!SUPABASE_URL || !SUPABASE_ANON_KEY)) {
  throw new Error('VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are required')
}

if (!['supabase', 'local'].includes(AUTH_PROVIDER)) {
  throw new Error("VITE_AUTH_PROVIDER must be either 'supabase' or 'local'")
}
