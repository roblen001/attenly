import { API_BASE_URL } from "./configs";
import { supabase } from "./supabase";

interface ApiOptions extends RequestInit {
  nonCritical?: boolean; // If true, 401 errors won't sign out the user
}

export async function api(path: string, init: ApiOptions = {}) {
  const { nonCritical = false, ...requestInit } = init;
  
  // Get the current session token with basic retry logic
  let session = null;
  let retryCount = 0;
  const maxRetries = 3;
  
  while (retryCount < maxRetries && !session) {
    const { data: { session: currentSession }, error } = await supabase.auth.getSession();
    
    if (error) {
      console.warn(`Session retrieval error (attempt ${retryCount + 1}):`, error);
    }
    
    if (currentSession?.access_token) {
      session = currentSession;
      break;
    }
    
    retryCount++;
    if (retryCount < maxRetries) {
      // Wait a bit before retrying
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }
  const headers: HeadersInit = {
    ...(init.headers as Record<string, string> || {}),
  };
  
  // Only set Content-Type for non-FormData requests
  // FormData requests need the browser to set multipart/form-data with boundary
  if (!(init.body instanceof FormData)) {
    (headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  
  // Add Authorization header if user is authenticated
  if (session?.access_token) {
    (headers as Record<string, string>).Authorization = `Bearer ${session.access_token}`;
  } else {
    console.warn('No valid session found for API call to:', path);
  }
  
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...requestInit,
    headers,
  });
  
  // Handle authentication errors
  if (res.status === 401) {
    console.error('Authentication failed for API call:', {
      path,
      nonCritical,
      hasSession: !!session,
      hasToken: !!session?.access_token,
      retryCount,
      timestamp: new Date().toISOString()
    });
    
    // For non-critical API calls, don't sign out the user
    if (nonCritical) {
      console.warn('Non-critical API call failed with 401, not signing out user');
      throw new Error('Authentication failed for non-critical API call');
    }
    
    // For critical API calls, sign out user and redirect
    const currentPath = window.location.pathname;
    if (currentPath !== '/login' && currentPath !== '/') {
      console.log('Signing out user and redirecting to login due to 401 error');
      
      // Sign out the user and clear session
      await supabase.auth.signOut();
      
      // Redirect to login page
      window.location.href = '/login';
    } else {
      console.warn('Already on login/landing page, not redirecting to prevent loop');
    }
    
    // Throw error with clear message
    throw new Error('Authentication failed. Please log in again.');
  }
  if (!res.ok)
    throw new Error(`${res.status} ${await res.text().catch(() => "")}`);
  return res;
}
