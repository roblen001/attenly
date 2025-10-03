# Implementation Plan

## Overview
Implement invite-only user signup flow by adding password reset functionality to the existing Supabase authentication system. This enables invited users to set their initial password through email reset links while maintaining the current authentication architecture.

The implementation adds password reset capabilities to the existing Login page, creates callback handling for email reset links, and provides route protection through an AuthGate component. The existing signup UI is preserved since public signups are already disabled at the Supabase level.

## Types
Define TypeScript interfaces for authentication state and callback handling.

```typescript
// Frontend authentication types
interface AuthState {
  session: Session | null;
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
}

interface PasswordResetData {
  email: string;
  redirectTo: string;
}

interface AuthCallbackResult {
  session: Session | null;
  error: AuthError | null;
}
```

## Files
Modify existing authentication files and create new components for callback handling and route protection.

### Modified Files:
- `frontend/src/libs/supabase.ts` - Update client configuration with required auth flags
- `frontend/src/pages/Login.tsx` - Add password reset functionality to existing login form
- `frontend/.env.example` - Add auth redirect environment variable example
- `frontend/src/App.tsx` (or main router file) - Add callback route and AuthGate integration

### New Files:
- `frontend/src/pages/AuthCallback.tsx` - Handle password reset email callbacks
- `frontend/src/components/AuthGate.tsx` - Protect authenticated routes
- `frontend/src/components/AuthGate.css` - Styling for auth gate loading states

## Functions
Enhance existing authentication functions and add new password reset capabilities.

### Modified Functions:
- `frontend/src/libs/supabase.ts`:
  - Update `createClient()` configuration with `detectSessionInUrl: true`
- `frontend/src/pages/Login.tsx`:
  - Add `sendSetPassword()` function for password reset emails
  - Update form submission handling for reset flow

### New Functions:
- `frontend/src/pages/AuthCallback.tsx`:
  - `handleAuthCallback()` - Process email callback and redirect appropriately
- `frontend/src/components/AuthGate.tsx`:
  - `checkAuthState()` - Validate session and handle redirects
  - `AuthGate()` component - Wrap protected routes with authentication check

## Classes
No new classes required. Implementation uses functional components with hooks.

## Dependencies
No new dependencies required. Uses existing Supabase and React Router packages.

The implementation leverages:
- `@supabase/supabase-js` - Already installed for authentication
- `react-router-dom` - Already installed for navigation
- `react` hooks - useState, useEffect, useNavigate for state management

## Testing
Test password reset flow and authentication state management.

### Test Scenarios:
1. **Password Reset Flow**:
   - Send reset email from login page
   - Click reset link in email
   - Verify callback handling and session creation
   - Test navigation to dashboard after successful reset

2. **Route Protection**:
   - Access protected route without authentication
   - Verify redirect to login page
   - Test authenticated access to protected routes
   - Validate session persistence across page refreshes

3. **Environment Configuration**:
   - Verify auth redirect URL configuration
   - Test callback URL handling in different environments

## Implementation Order
Sequential implementation to ensure proper integration and testing at each step.

1. **Step 1: Environment Configuration**
   - Add `VITE_AUTH_REDIRECT` environment variable to example and documentation
   - Update frontend environment configuration

2. **Step 2: Supabase Client Enhancement** 
   - Update `frontend/src/libs/supabase.ts` with required auth configuration flags
   - Test client initialization and session detection

3. **Step 3: AuthCallback Component Creation**
   - Create `frontend/src/pages/AuthCallback.tsx` for handling email reset callbacks
   - Implement session detection and navigation logic
   - Test callback URL processing

4. **Step 4: AuthGate Component Creation**
   - Create `frontend/src/components/AuthGate.tsx` for route protection
   - Implement authentication state checking and redirect logic
   - Add loading states and error handling

5. **Step 5: Login Page Enhancement**
   - Modify existing `frontend/src/pages/Login.tsx` to add password reset functionality
   - Add "Set/Forgot Password" button and form handling
   - Integrate reset email sending with proper redirect URL

6. **Step 6: Router Integration**
   - Add `/auth/callback` route to main router
   - Integrate AuthGate component with protected routes
   - Test route protection and callback handling

7. **Step 7: Testing and Validation**
   - Test complete password reset flow from email to dashboard
   - Validate route protection works correctly
   - Verify session persistence and authentication state management
