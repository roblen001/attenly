import { API_BASE_URL } from "./configs";
import { authClient, isLocalAuthProvider, isTokenAuthProvider, storeAuthError } from "./auth";

interface ApiOptions extends RequestInit {
  nonCritical?: boolean; // If true, 401 errors won't sign out the user
  timeout?: number; // Request timeout in milliseconds (default: 30000)
  retries?: number; // Number of retries for GET requests (default: 2)
}

export async function api(path: string, init: ApiOptions = {}) {
  const { nonCritical = false, timeout = 600000, retries = 2, ...requestInit } = init;
  
  // Get the current session token with basic retry logic
  let session = null;
  let retryCount = 0;
  const maxRetries = 3;
  
  while (retryCount < maxRetries && !session) {
    const { data: { session: currentSession }, error } = await authClient.getSession();
    
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
    // Include a refresh token when the selected backend auth/storage adapter needs it.
    if (session?.refresh_token) {
      (headers as Record<string, string>)['X-Refresh-Token'] = session.refresh_token;
    }
  } else {
    console.warn('No valid session found for API call to:', path);
  }
  
  // Helper function to make a fetch request with timeout
  const makeRequest = async (): Promise<Response> => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
      const response = await fetch(`${API_BASE_URL}${path}`, {
        ...requestInit,
        headers,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  };

  // Retry logic for GET requests only
  let res: Response;
  const isGetRequest = !requestInit.method || requestInit.method.toUpperCase() === 'GET';
  
  if (isGetRequest && retries > 0) {
    let attempts = 0;
    const maxAttempts = retries + 1;
    let lastError: Error | null = null;
    
    while (attempts < maxAttempts) {
      try {
        res = await makeRequest();
        break;
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        attempts++;
        if (attempts >= maxAttempts) {
          throw lastError;
        }
        // Wait before retrying (exponential backoff)
        await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempts - 1) * 1000));
      }
    }
    
    // TypeScript safety: ensure res is assigned
    if (!res!) {
      throw lastError || new Error('Request failed after retries');
    }
  } else {
    res = await makeRequest();
  }
  
  // Handle authentication errors
  if (res.status === 401) {
    let backendDetail = '';
    try {
      const body = await res.json() as { detail?: unknown };
      backendDetail = typeof body.detail === 'string' ? body.detail : '';
    } catch {
      // Fall back to the user-facing message below.
    }
    const authError = isLocalAuthProvider
      ? 'Your access token is invalid or no longer accepted. Enter the current deployment access token.'
      : isTokenAuthProvider
      ? 'Your identity token is invalid or no longer accepted. Enter a current identity token.'
      : backendDetail || 'Your session is no longer valid. Please sign in again.';

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
      throw new Error(authError);
    }
    
    // For critical API calls, sign out user and redirect
    const currentPath = window.location.pathname;
    if (currentPath !== '/login' && currentPath !== '/') {
      console.log('Signing out user and redirecting to login due to 401 error');
      
      storeAuthError(authError);

      // Sign out the user and clear session
      await authClient.signOut();
      
      // Redirect to login page
      window.location.href = '/login';
    } else {
      console.warn('Already on login/landing page, not redirecting to prevent loop');
    }
    
    // Throw error with clear message
    throw new Error(authError);
  }
  if (!res.ok)
    throw new Error(`${res.status} ${await res.text().catch(() => "")}`);
  return res;
}
