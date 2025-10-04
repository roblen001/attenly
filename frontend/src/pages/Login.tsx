import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { supabase } from "../libs/supabase";
import { useAuth } from "../feature/auth/useAuth";
import "./Login.css";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, isPasswordRecovery } = useAuth();
  const [isSignUp, setIsSignUp] = useState(false);
  const [isPasswordReset, setIsPasswordReset] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  // Check for password reset success
  useEffect(() => {
    const searchParams = new URLSearchParams(location.search);
    if (searchParams.get('reset') === 'success') {
      setMessage("Your password has been updated successfully. Please sign in with your new password.");
    }
  }, [location.search]);

  // Redirect if already authenticated
  if (isAuthenticated && !isPasswordRecovery) {
    const from = location.state?.from?.pathname || '/dashboard';
    navigate(from, { replace: true });
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");

    try {
      if (isPasswordReset) {
        // Handle password reset
        const { error } = await supabase.auth.resetPasswordForEmail(email, {
          redirectTo: `${window.location.origin}/auth/callback?type=recovery`,
        });

        if (error) {
          setError(error.message);
        } else {
          setMessage("Check your email for the password reset link!");
        }
      } else if (isSignUp) {
        if (password !== confirmPassword) {
          setError("Passwords do not match");
          setLoading(false);
          return;
        }

        const { error } = await supabase.auth.signUp({
          email,
          password,
        });

        if (error) {
          setError(error.message);
        } else {
          setMessage("Check your email for the confirmation link!");
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({
          email,
          password,
        });

        if (error) {
          setError(error.message);
        } else {
          const from = location.state?.from?.pathname || '/dashboard';
          navigate(from, { replace: true });
        }
      }
    } catch {
      setError("An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  const toggleMode = () => {
    setIsSignUp(!isSignUp);
    setIsPasswordReset(false);
    setError("");
    setMessage("");
    setEmail("");
    setPassword("");
    setConfirmPassword("");
  };

  const togglePasswordReset = () => {
    setIsPasswordReset(!isPasswordReset);
    setIsSignUp(false);
    setError("");
    setMessage("");
    setEmail("");
    setPassword("");
    setConfirmPassword("");
  };

  return (
    <div className="login-page">
      {/* Hero Background */}
      <div className="login-hero">
        <div className="hero-background">
          <div className="hero-gradient"></div>
          <div className="hero-pattern"></div>
        </div>

        <div className="login-container">
          {/* Branding Section */}
          <div className="login-branding">
            <div className="brand-badge">
              <span className="badge-icon">🏢</span>
              <span>Attenly</span>
            </div>
            <h1 className="brand-title">
              Welcome to <span className="title-highlight">Attenly</span>
            </h1>
            <p className="brand-description">
              AI-powered data extraction for professional reports
            </p>
          </div>

          {/* Login Form */}
          <div className="login-form-container">
            <div className="form-header">
              <h2 className="form-title">
                {isPasswordReset ? "Reset Password" : isSignUp ? "Create Account" : "Sign In"}
              </h2>
              <p className="form-subtitle">
                {isPasswordReset
                  ? "Enter your email to receive a password reset link"
                  : isSignUp 
                  ? "Get started with your professional workflow" 
                  : "Continue to your dashboard"
                }
              </p>
            </div>

            <form onSubmit={handleSubmit} className="login-form">
              <div className="form-group">
                <label htmlFor="email" className="form-label">
                  Email Address
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="form-input"
                  placeholder="Enter your email"
                  required
                />
              </div>

              {!isPasswordReset && (
                <div className="form-group">
                  <label htmlFor="password" className="form-label">
                    Password
                  </label>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="form-input"
                    placeholder="Enter your password"
                    required
                  />
                </div>
              )}

              {isSignUp && !isPasswordReset && (
                <div className="form-group">
                  <label htmlFor="confirmPassword" className="form-label">
                    Confirm Password
                  </label>
                  <input
                    id="confirmPassword"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="form-input"
                    placeholder="Confirm your password"
                    required
                  />
                </div>
              )}

              {error && (
                <div className="form-message error-message">
                  <span className="message-icon">⚠️</span>
                  {error}
                </div>
              )}

              {message && (
                <div className="form-message success-message">
                  <span className="message-icon">✅</span>
                  {message}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="form-submit-btn"
              >
                {loading ? (
                  <>
                    <span className="loading-spinner"></span>
                    {isPasswordReset ? "Sending Reset Link..." : isSignUp ? "Creating Account..." : "Signing In..."}
                  </>
                ) : (
                  <>
                    <span className="btn-icon">
                      {isPasswordReset ? "🔐" : isSignUp ? "🚀" : "✨"}
                    </span>
                    {isPasswordReset ? "Send Reset Link" : isSignUp ? "Create Account" : "Sign In"}
                    <span className="btn-arrow">→</span>
                  </>
                )}
              </button>
            </form>

            <div className="form-footer">
              {!isPasswordReset ? (
                <>
                  <p className="toggle-text">
                    {isSignUp ? "Already have an account?" : "Don't have an account?"}
                    <button
                      type="button"
                      onClick={toggleMode}
                      className="toggle-btn"
                    >
                      {isSignUp ? "Sign In" : "Sign Up"}
                    </button>
                  </p>
                  {!isSignUp && (
                    <p className="toggle-text">
                      Need to set or reset your password?
                      <button
                        type="button"
                        onClick={togglePasswordReset}
                        className="toggle-btn"
                      >
                        Reset Password
                      </button>
                    </p>
                  )}
                </>
              ) : (
                <p className="toggle-text">
                  Remember your password?
                  <button
                    type="button"
                    onClick={togglePasswordReset}
                    className="toggle-btn"
                  >
                    Sign In
                  </button>
                </p>
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
