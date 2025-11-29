import "./App.css";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";
import LandingPage from "./pages/LandingPage";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import AuthCallback from "./pages/AuthCallback";
import AuthGate from "./components/AuthGate";
import { useAuth } from "./feature/auth/useAuth";
import AgentExecutionPage from "./pages/AgentExecution";
import ReportView from "./pages/ReportView";
import CreateAgent from "./pages/CreateAgent";
import EmailIngestSettings from "./pages/EmailIngestSettings";

export default function App() {
  const { isAuthenticated, loading, isPasswordRecovery } = useAuth(); 


  if (loading) {
    return (
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center', 
        height: '100vh',
        fontSize: '1.2rem'
      }}>
        Loading...
      </div>
    );
  }

  return (
    <Router>
      <Routes>
        {/* Public Routes */}
        <Route
          path="/"
          element={
            isPasswordRecovery ? (
              <Navigate to="/auth/callback" replace />
            ) : isAuthenticated ? (
              <Navigate to="/dashboard" replace />
            ) : (
              <LandingPage />
            )
          }
        />

        <Route
          path="/login"
          element={
            isPasswordRecovery ? (
              <Navigate to="/auth/callback" replace />
            ) : isAuthenticated ? (
              <Navigate to="/dashboard" replace />
            ) : (
              <Login />
            )
          }
        />

        {/* Auth Callback Route — only valid during recovery */}
        <Route
          path="/auth/callback"
          element={
            isPasswordRecovery ? (
              <AuthCallback />
            ) : isAuthenticated ? (
              <Navigate to="/dashboard" replace />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />

        {/* Protected Routes */}
        <Route
          path="/dashboard"
          element={
            <AuthGate>
              <Dashboard />
            </AuthGate>
          }
        />

        <Route 
          path="/agent-execution/:agentId" 
          element={
            <AuthGate>
              <AgentExecutionPage />
            </AuthGate>
          }
        />

        <Route 
          path="/report/:agentId" 
          element={
            <AuthGate>
              <ReportView />
            </AuthGate>
          }
        />

        <Route 
          path="/report/saved/:reportId" 
          element={
            <AuthGate>
              <ReportView />
            </AuthGate>
          }
        />

        <Route 
          path="/create-agent" 
          element={
            <AuthGate>
              <CreateAgent />
            </AuthGate>
          }
        />

        <Route 
          path="/create-agent/:agentId" 
          element={
            <AuthGate>
              <CreateAgent />
            </AuthGate>
          }
        />

        <Route 
          path="/settings/email-ingest" 
          element={
            <AuthGate>
              <EmailIngestSettings />
            </AuthGate>
          }
        />

        {/* Optional: 404 catch-all */}
        <Route path="*" element={<Navigate to="/" replace />} />

      </Routes>
    </Router>
  );
}
