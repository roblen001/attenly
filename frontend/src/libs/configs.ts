export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
export const AUTH_PROVIDER = (import.meta.env.VITE_AUTH_PROVIDER || 'supabase').toLowerCase()
export const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL
export const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY
export const LOCAL_AUTH_USER_ID = import.meta.env.VITE_LOCAL_AUTH_USER_ID || 'local-admin'
export const LOCAL_AUTH_EMAIL = import.meta.env.VITE_LOCAL_AUTH_EMAIL || 'local-admin@example.com'
export const LOCAL_AUTH_DISPLAY_NAME = import.meta.env.VITE_LOCAL_AUTH_DISPLAY_NAME || 'Local Admin'
export const LOCAL_AUTH_TOKEN_PREFILL = import.meta.env.VITE_LOCAL_AUTH_TOKEN || ''

// Production safety check
if (import.meta.env.PROD && API_BASE_URL && !API_BASE_URL.startsWith('https://')) {
  throw new Error('Production API_BASE_URL must use HTTPS')
}

// Validate required environment variables
if (AUTH_PROVIDER === 'supabase' && (!SUPABASE_URL || !SUPABASE_ANON_KEY)) {
  throw new Error('VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are required')
}

if (!['supabase', 'local'].includes(AUTH_PROVIDER)) {
  throw new Error("VITE_AUTH_PROVIDER must be either 'supabase' or 'local'")
}
