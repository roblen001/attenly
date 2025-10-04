import { useEffect, useState } from 'react';
import { supabase } from '../../libs/supabase';
import type { Session } from '@supabase/supabase-js';

export function useAuth() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [isPasswordRecovery, setIsPasswordRecovery] = useState(false);

  useEffect(() => {
    // Get initial session
    supabase.auth.getSession().then(({ data, error }) => {
      if (error) {
        console.warn('Initial session retrieval error:', error);
      }
      console.log('Initial session loaded:', data.session ? 'Session exists' : 'No session');
      setSession(data.session);
      setLoading(false);
    });

    // Listen for auth state changes
    const { data: sub } = supabase.auth.onAuthStateChange((event, sess) => {
      console.log('Auth state change:', event, sess ? 'Session exists' : 'No session');
      
      if (event === 'PASSWORD_RECOVERY') {
        console.log('Password recovery detected - blocking authentication until reset complete');
        setIsPasswordRecovery(true);
        setSession(sess);
        setLoading(false);
        return;
      }
      
      // Don't reset password recovery state during INITIAL_SESSION events
      if (event === 'INITIAL_SESSION' && isPasswordRecovery) {
        console.log('Initial session during password recovery - maintaining recovery state');
        setSession(sess);
        setLoading(false);
        return;
      }
      
      if (event === 'SIGNED_IN' && isPasswordRecovery) {
        console.log('Password recovery completed - user now authenticated');
        setIsPasswordRecovery(false);
      }
      
      setSession(sess);
      setLoading(false);
    });

    return () => sub.subscription.unsubscribe();
  }, [isPasswordRecovery]);

  const signIn = (email: string, password: string) =>
    supabase.auth.signInWithPassword({ email, password });

  const signOut = async () => {
    setLoading(true);
    await supabase.auth.signOut();
    setIsPasswordRecovery(false);
    // Session will be updated via onAuthStateChange
  };

  // Don't consider user authenticated during password recovery
  const isAuthenticated = !!session?.user && !isPasswordRecovery;

  return { 
    session, 
    signIn, 
    signOut, 
    user: session?.user ?? null,
    loading,
    isAuthenticated,
    isPasswordRecovery
  };
}
