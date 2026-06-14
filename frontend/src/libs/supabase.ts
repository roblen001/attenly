import { createClient } from '@supabase/supabase-js';
import { AUTH_PROVIDER, SUPABASE_ANON_KEY, SUPABASE_URL } from './configs';

export const supabase = AUTH_PROVIDER === 'supabase'
  ? createClient(
      SUPABASE_URL!,
      SUPABASE_ANON_KEY!,
      {
        auth: {
          detectSessionInUrl: true,
          persistSession: true,
          autoRefreshToken: true,
        }
      }
    )
  : null;
