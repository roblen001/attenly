// src/pages/Dashboard.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../libs/https";
import { useAuth } from "../feature/auth/useAuth";
import type { Agent } from '../types';
import './Dashboard.css';
import PrebuiltAgentCard from '../components/dashboard/PrebuiltAgentCard';
import SavedReportCard from '../components/dashboard/SavedReportCard';

// TODO BEFORE LAUNCH: important to adjust supabase polecies to include email confirmation and what not
export default function Dashboard() {
  const { loading: authLoading, session } = useAuth();
  const navigate = useNavigate();
  const [prebuiltAgents, setPrebuiltAgents] = useState<Agent[]>([]);
  const [savedReports, setSavedReports] = useState<any[]>([]);
  const [loadingSavedReports, setLoadingSavedReports] = useState(false);

  const handleExecuteAgent = (agent: Agent) => {
    navigate(`/agent-execution/${agent.id}`);
  };

  const handleViewSavedReport = (reportId: string) => {
    navigate(`/report/saved/${reportId}`);
  };

  const handleDeleteSavedReport = async (reportId: string) => {
    try {
      const response = await api(`/agents/reports/saved/${reportId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error('Failed to delete report');
      }

      // Remove from local state
      setSavedReports(prev => prev.filter(report => report.id !== reportId));
      console.log('Report deleted successfully');
    } catch (error) {
      console.error('Failed to delete report:', error);
      alert('Failed to delete report. Please try again.');
    }
  };

  const handleDownloadSavedReport = async (reportId: string) => {
    try {
      const response = await api(`/agents/reports/saved/${reportId}/pdf`);

      if (!response.ok) {
        throw new Error('Failed to download report');
      }

      // Create blob and download
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;

      // Get filename from response headers
      const contentDisposition = response.headers.get('content-disposition');
      let filename = 'saved_report.pdf';
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename=([^;]+)/);
        if (filenameMatch) {
          filename = filenameMatch[1].replace(/"/g, '');
        }
      }

      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

    } catch (error) {
      console.error('Failed to download report:', error);
      alert('Failed to download report. Please try again.');
    }
  };

  useEffect(() => {
    // Wait for auth to be ready AND session to exist before making API calls
    if (authLoading || !session) {
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

    async function loadSavedReports() {
      try {
        setLoadingSavedReports(true);
        const res = await api("/agents/reports/saved", {
          method: "GET",
          headers: { Accept: "application/json" },
          signal: controller.signal,
          nonCritical: true, // Don't sign out user if this API call fails
        });

        if (!res.ok) {
          const msg = await res.text().catch(() => "");
          console.error("Failed to load saved reports:", res.status, msg);
          setSavedReports([]);
          return;
        }

        const reports = await res.json();
        setSavedReports(reports);
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          console.error("Error loading saved reports:", err);
          setSavedReports([]);
        }
      } finally {
        setLoadingSavedReports(false);
      }
    }

    loadPrebuiltAgents();
    loadSavedReports();
    return () => controller.abort();
  }, [authLoading, session]);

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

          {/* Saved Reports Section */}
          <div className="saved-reports-section">
            <div className="section-header">
              <h2 className="section-title">
                <span className="section-icon">📊</span>
                My Saved Reports
              </h2>
              <p className="section-subtitle">
                Access your previously generated and saved reports
              </p>
            </div>

            {loadingSavedReports ? (
              <div className="loading-state">
                <p>Loading saved reports...</p>
              </div>
            ) : savedReports.length > 0 ? (
              <div className="saved-reports-grid">
                {savedReports.map((report) => (
                  <SavedReportCard
                    key={report.id}
                    report={report}
                    onDelete={handleDeleteSavedReport}
                    onDownload={handleDownloadSavedReport}
                    onClick={() => handleViewSavedReport(report.id)}
                  />
                ))}
              </div>
            ) : (
              <div className="saved-reports-empty">
                <h3>No saved reports yet</h3>
                <p>Generate and save reports to see them here</p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
