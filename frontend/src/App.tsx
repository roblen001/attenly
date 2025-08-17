import "./App.css";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import LandingPage from "./pages/LandingPage";
import Dashboard from "./pages/Dashboard";
import AgentExecutionPage from "./pages/AgentExecution";

export default function App() {
  return (
    <Router>
      <div>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/agent-execution/:agentId" element={<AgentExecutionPage />} />
        </Routes>
      </div>
    </Router>
  );
}
