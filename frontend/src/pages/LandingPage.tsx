import { useNavigate } from "react-router-dom";
import "./LandingPage.css";
import { supabase } from "../libs/supabase";
import { useEffect } from "react";

export default function LandingPage() {
  const navigate = useNavigate();

  // TODO question: this redirects on page load if not login, is this necessar or should I just leave it up to when the user to clickse "Get Started"?
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) navigate("/dashboard");
    });
  }, []);

  const handleGetStarted = async () => {
    try {
      const { data, error } = await supabase.auth.getSession();
      if (error) throw error;

      if (data.session) {
        navigate("/dashboard");
      } else {
        navigate("/login");
      }
    } catch (error) {
      console.error("Error during authentication:", error);
      alert("Something went wrong. Please try again.");
    }
  };

  return (
    <div className="landing-page">
      {/* Full Screen Hero Section */}
      <div className="landing-hero">
        <div className="hero-background">
          <div className="hero-gradient"></div>
          <div className="hero-pattern"></div>
        </div>
        <div className="hero-content">
          <div className="hero-badge">
            <span className="badge-icon">🏢</span>
            <span>Built for Underwriters</span>
          </div>
          <h1 className="hero-title">
            AI Extracts the Data,
            <span className="title-highlight"> You Design the Reports</span>
          </h1>
          <p className="hero-description">
            Streamline underwriting workflows with intelligent data extraction
            from policy documents, loss runs, and submissions. AI finds the
            information, you customize how it's presented in professional
            reports.
          </p>

          <div className="hero-features">
            <div className="feature-grid">
              <div className="feature-item">
                <div className="feature-icon">🔍</div>
                <h3>Attenly for Intelligent Data Extraction</h3>
                <p>
                  AI automatically finds policy numbers, loss amounts, coverage
                  details, and key underwriting data
                </p>
              </div>
              <div className="feature-item">
                <div className="feature-icon">🎨</div>
                <h3>Visual Report Builder</h3>
                <p>
                  Drag-and-drop interface to customize layouts, styling, and
                  organization exactly how you need it
                </p>
              </div>
              <div className="feature-item">
                <div className="feature-icon">📋</div>
                <h3>Professional Output</h3>
                <p>
                  Generate polished underwriting reports that match your
                  workflow and branding standards
                </p>
              </div>
            </div>
          </div>

          <div className="hero-cta-section">
            <button onClick={handleGetStarted} className="hero-cta-btn">
              <span className="cta-icon">✨</span>
              Get Started
              <span className="cta-arrow">→</span>
            </button>
            <p className="cta-subtitle">
              Transform your underwriting workflow in minutes
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
