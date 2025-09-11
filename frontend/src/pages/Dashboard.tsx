// src/pages/Dashboard.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../libs/https";
import { useAuth } from "../feature/auth/useAuth";
import type { Agent } from '../types';
import './Dashboard.css';
import PrebuiltAgentCard from '../components/dashboard/PrebuiltAgentCard';

// TODO BEFORE LAUNCH: important to adjust supabase polecies to include email confirmation and what not
export default function Dashboard() {
  const { loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [prebuiltAgents, setPrebuiltAgents] = useState<Agent[]>([]);

  const handleExecuteAgent = (agent: Agent) => {
    navigate(`/agent-execution/${agent.id}`);
  };

  useEffect(() => {
    // Wait for auth to be ready before making API calls
    if (authLoading) {
      return;
    }

    const controller = new AbortController();

    async function loadPrebuiltAgents() {
      try {
        const res = await api("/agents/prebuilt", {
          method: "GET",
          headers: { Accept: "application/json" },
          signal: controller.signal,
        });

        if (!res.ok) {
          const msg = await res.text().catch(() => "");
          console.error("Failed to load prebuilt agents:", res.status, msg);
          setPrebuiltAgents([]);
          return;
        }

        const list = (await res.json()) as Agent[];    
        const agents: Agent[] = list.map((a) => ({
          ...a,
        }));

        setPrebuiltAgents(agents);
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          console.error("Error loading prebuilt agents:", err);
          setPrebuiltAgents([]);
        }
      }
    }

    loadPrebuiltAgents();
    return () => controller.abort();
  }, [authLoading]);

  return (
    <div className="modern-dashboard">
      <main className="dashboard-main">
        <div className="dashboard-container">
          {/* Featured Templates Section */}
          <div className="featured-templates-section">
            <div className="section-header">
              <h2 className="section-title">
                <span className="section-icon">⭐</span>
                Featured Agents
              </h2>
              <p className="section-subtitle">
                Start with these proven agents, then customize to your needs
              </p>
            </div>

            <div className="templates-grid">
              {prebuiltAgents.map((template) => (
                <PrebuiltAgentCard
                  key={template.id}
                  onSelectAgent={handleExecuteAgent}
                  agent={template}
                />
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
