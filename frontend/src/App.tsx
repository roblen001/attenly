import "./App.css";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";
import LandingPage from "./pages/LandingPage";
import Dashboard from "./pages/Dashboard";
import { useAuth } from "./feature/auth/useAuth";
import { Auth } from "@supabase/auth-ui-react";
import { ThemeSupa } from "@supabase/auth-ui-shared";
import { supabase } from "./libs/supabase";
import AgentExecutionPage from "./pages/AgentExecution";
import ReportView from "./pages/ReportView";
import CreateAgent from "./pages/CreateAgent";

export default function App() {
  const { session, loading } = useAuth();

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
        <Route
          path="/"
          element={
            session ? (
              <Navigate to="/dashboard" replace />
            ) : (
              <LandingPage session={session} />
            )
          }
        />

        <Route
          path="/login"
          element={
            session ? (
              <Navigate to="/dashboard" replace />
            ) : (
              <Auth
                supabaseClient={supabase}
                appearance={{ theme: ThemeSupa }}
                providers={[]}
              />
            )
          }
        />

        <Route
          path="/dashboard"
          element={
            session ? (
              <Dashboard />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />

        <Route 
          path="/agent-execution/:agentId" 
          element={
            session ? (
              <AgentExecutionPage />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />

        <Route 
          path="/report/:agentId" 
          element={
            session ? (
              <ReportView />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />

        <Route 
          path="/report/saved/:reportId" 
          element={
            session ? (
              <ReportView />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />

        <Route 
          path="/create-agent" 
          element={
            session ? (
              <CreateAgent />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />

      </Routes>
    </Router>
  );
}
