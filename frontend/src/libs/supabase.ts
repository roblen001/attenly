// TODO createClient with anon key
import { createClient } from '@supabase/supabase-js';

export const supabase_client = createClient(
  import.meta.env.VITE_SUPABASE_URL!,
  import.meta.env.VITE_SUPABASE_ANON_KEY!
);



