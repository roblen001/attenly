import { useState, useEffect } from 'react';
import type { PrebuiltAgentOut } from '../types';
import PrebuiltAgentCard from '../components/dashboard/PrebuiltAgentCard';
import './Dashboard.css';
import { api } from "../libs/https";

export default function Dashboard() {
  const [prebuiltAgents, setPrebuiltAgents] = useState<PrebuiltAgentOut[]>([]);

  useEffect(() => {
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

        const list = (await res.json()) as PrebuiltAgentOut[];    
        const agents: PrebuiltAgentOut[] = list.map((a) => ({
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
  }, []);

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
