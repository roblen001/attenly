import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { supabase } from "../libs/supabase";
import "./Login.css";

export default function Login() {
  const navigate = useNavigate();
  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");

    try {
      if (isSignUp) {
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
          navigate("/dashboard");
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
                {isSignUp ? "Create Account" : "Sign In"}
              </h2>
              <p className="form-subtitle">
                {isSignUp 
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

              {isSignUp && (
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
                    {isSignUp ? "Creating Account..." : "Signing In..."}
                  </>
                ) : (
                  <>
                    <span className="btn-icon">
                      {isSignUp ? "🚀" : "✨"}
                    </span>
                    {isSignUp ? "Create Account" : "Sign In"}
                    <span className="btn-arrow">→</span>
                  </>
                )}
              </button>
            </form>

            <div className="form-footer">
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
            </div>
          </div>
        </div>

        {/* Back to Landing */}
        <div className="back-to-landing">
          <button
            onClick={() => navigate("/")}
            className="back-btn"
          >
            <span className="back-icon">←</span>
            Back to Home
          </button>
        </div>
      </div>
    </div>
  );
}
