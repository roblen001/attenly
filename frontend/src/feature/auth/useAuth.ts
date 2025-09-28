import { useEffect, useState } from 'react';
import { supabase } from '../../libs/supabase';
import type { Session } from '@supabase/supabase-js';

export function useAuth() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Get initial session
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });

    // Listen for auth state changes
    const { data: sub } = supabase.auth.onAuthStateChange((_event, sess) => {
      setSession(sess);
      setLoading(false);
    });

    return () => sub.subscription.unsubscribe();
  }, []);

  const signIn = (email: string, password: string) =>
    supabase.auth.signInWithPassword({ email, password });

  const signOut = async () => {
    setLoading(true);
    await supabase.auth.signOut();
    // Session will be updated via onAuthStateChange
  };

  const isAuthenticated = !!session?.user;

  return { 
    session, 
    signIn, 
    signOut, 
    user: session?.user ?? null,
    loading,
    isAuthenticated
  };
}
