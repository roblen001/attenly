import { useNavigate } from "react-router-dom";
import "./LandingPage.css";
import type { Session } from "@supabase/supabase-js";

export default function LandingPage({ session }: { session: Session | null }) {
  const navigate = useNavigate();

  const handleGetStarted = async () => {
    if (session) {
      navigate("/dashboard");
    } else {
      navigate("/login");
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
            <span>Built for Professionals</span>
          </div>
          <h1 className="hero-title">
            AI Extracts the Data,
            <span className="title-highlight"> You Design the Reports</span>
          </h1>
            <p className="hero-description">
            Streamline corporate workflows with intelligent data extraction from complex documents. AI finds the information, you customize how it's presented in professional reports.
            </p>

          <div className="hero-features">
            <div className="feature-grid">
              <div className="feature-item">
                <div className="feature-icon">🔍</div>
                <h3>Attenly for Intelligent Data Extraction</h3>
                <p>
                  AI automatically finds important details, figures, and key data from your documents
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
                  Generate polished reports that match your
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
              Transform your workflow in minutes
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
