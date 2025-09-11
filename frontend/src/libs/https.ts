import { API_BASE_URL } from "./configs";
import { supabase } from "./supabase";

export async function api(path: string, init: RequestInit = {}) {
  // Get the current session token
  const { data: { session } } = await supabase.auth.getSession();
  
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
  }
  
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers,
    ...init,
  });
  
  // Handle authentication errors
  if (res.status === 401) {
    console.log('Authentication failed - signing out user');
    
    // Sign out the user and clear session
    await supabase.auth.signOut();
    
    // Redirect to login page
    window.location.href = '/login';
    
    // Throw error with clear message
    throw new Error('Authentication failed. Please log in again.');
  }
  
  if (!res.ok)
    throw new Error(`${res.status} ${await res.text().catch(() => "")}`);
  return res;
}
