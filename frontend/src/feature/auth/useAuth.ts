import { useEffect, useState } from 'react';
import { supabase_client } from '../../libs/supabase';
import type { Session } from '@supabase/supabase-js';

export function useAuth() {
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    supabase_client.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = supabase_client.auth.onAuthStateChange((_event, sess) => setSession(sess));
    return () => sub.subscription.unsubscribe();
  }, []);

  const signIn = (email: string, password: string) =>
    supabase_client.auth.signInWithPassword({ email, password });

  const signOut = () => supabase_client.auth.signOut();

  return { session, signIn, signOut, user: session?.user ?? null };
}





