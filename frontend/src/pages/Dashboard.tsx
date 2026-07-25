// src/pages/Dashboard.tsx
import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router";
import { api } from "../libs/https";
import { useAuth } from "../feature/auth/useAuth";
import type { Agent } from '../types';
import './Dashboard.css';
import PrebuiltAgentCard from '../components/dashboard/PrebuiltAgentCard';
import CustomAgentCard from '../components/dashboard/CustomAgentCard';
import CompactReportList from '../components/dashboard/CompactReportList';

// Import types from the component files to reuse existing interfaces
interface CustomAgent {
  id: string;
  name: string;
  description: string;
  reportTemplate: string;
  questions: Array<{
    id: string;
    placeholder: string;
    prompt: string;
  }>;
  user_id: string;
  is_custom: boolean;
  created_by_name?: string;
  createdAt: string;
  updatedAt: string;
  can_delete: boolean;
}

interface SavedReport {
  id: string;
  report_name: string;
  agent_name: string;
  agent_id: string;
  saved_at: string;
  generated_at: string;
}

export default function Dashboard() {
  const { loading: authLoading, session, signOut } = useAuth();
  const navigate = useNavigate();
  const [prebuiltAgents, setPrebuiltAgents] = useState<Agent[]>([]);
  const [customAgents, setCustomAgents] = useState<CustomAgent[]>([]);
  const [loadingCustomAgents, setLoadingCustomAgents] = useState(false);
  const [savedReports, setSavedReports] = useState<SavedReport[]>([]);
  const [loadingSavedReports, setLoadingSavedReports] = useState(false);
  
  // Ref to track if API calls have been initiated to prevent duplicates
  const apiCallsInitiated = useRef(false);
  const customAgentsRef = useRef<CustomAgent[]>([]);
  const savedReportsRef = useRef<SavedReport[]>([]);
  // State and ref to track visibility and data loading times
  const [wasVisible, setWasVisible] = useState(true);
  const lastDataLoad = useRef<number>(0);

  useEffect(() => {
    customAgentsRef.current = customAgents;
  }, [customAgents]);

  useEffect(() => {
    savedReportsRef.current = savedReports;
  }, [savedReports]);

  const handleExecuteAgent = (agent: Agent) => {
    navigate(`/agent-execution/${agent.id}`);
  };

  const handleExecuteCustomAgent = (agent: CustomAgent) => {
    navigate(`/agent-execution/${agent.id}`);
  };

  const handleDeleteCustomAgent = async (agentId: string) => {
    try {
      const response = await api(`/agents/custom/${agentId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error('Failed to delete custom agent');
      }

      // Remove from local state
      setCustomAgents(prev => prev.filter(agent => agent.id !== agentId));
    } catch (error) {
      console.error('Failed to delete custom agent:', error);
      alert('Failed to delete custom agent. Please try again.');
    }
  };

  const handleEditCustomAgent = (agentId: string) => {
    navigate(`/create-agent/${agentId}`);
  };

  const handleViewSavedReport = (reportId: string) => {
    navigate(`/report/saved/${reportId}`);
  };

  const handleAuditSavedReport = (reportId: string) => {
    navigate(`/report/saved/${reportId}?mode=audit`);
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

  // Handle page visibility changes to prevent unnecessary reloads on tab switching
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && !wasVisible) {
        // Page became visible after being hidden
        // Only allow reload if data is older than 30 seconds (prevents excessive reloads)
        const now = Date.now();
        if (now - lastDataLoad.current > 30000) {
          apiCallsInitiated.current = false;
        }
        setWasVisible(true);
      } else if (document.visibilityState === 'hidden') {
        setWasVisible(false);
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [wasVisible]);

  // Reset API calls flag when auth state changes (for legitimate auth changes)
  useEffect(() => {
    // Only reset immediately for auth changes, not routine session validation
    if (!authLoading && session) {
      // Allow some time for auth state to stabilize before allowing reloads
      const timer = setTimeout(() => {
        // Only reset if we don't have recent data
        const now = Date.now();
        if (now - lastDataLoad.current > 10000) { // 10 seconds for auth changes
          apiCallsInitiated.current = false;
        }
      }, 1000);
      
      return () => clearTimeout(timer);
    }
  }, [authLoading, session]);

  useEffect(() => {
    // Wait for auth to be ready AND session to exist before making API calls
    if (authLoading || !session) {
      return;
    }

    // Prevent duplicate API calls from React StrictMode or multiple auth state changes
    if (apiCallsInitiated.current) {
      return;
    }

    apiCallsInitiated.current = true;
    lastDataLoad.current = Date.now(); // Track when we loaded data
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

    async function loadCustomAgents() {
      try {
        // Only show loading state if we don't have existing data or it's been a while
        const hasExistingData = customAgentsRef.current.length > 0;
        const shouldShowLoading = !hasExistingData || (Date.now() - lastDataLoad.current > 30000);
        
        if (shouldShowLoading) {
          setLoadingCustomAgents(true);
        }
        
        const res = await api("/agents/list_user_custom_agents", {
          method: "GET",
          headers: { Accept: "application/json" },
          signal: controller.signal,
          nonCritical: true, // Don't sign out user if this API call fails
        });
        
        if (!res.ok) {
          const msg = await res.text().catch(() => "");
          console.error("Failed to load custom agents:", res.status, msg);
          // Only clear existing data if we don't have any or the call was expected to refresh
          if (!hasExistingData) {
            setCustomAgents([]);
          }
          return;
        }

        const agents = await res.json();
        setCustomAgents(agents);
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          console.error("Error loading custom agents:", err);
          // Only clear existing data if we don't have any
          if (customAgentsRef.current.length === 0) {
            setCustomAgents([]);
          }
        }
      } finally {
        setLoadingCustomAgents(false);
      }
    }

    async function loadSavedReports() {
      try {
        // Only show loading state if we don't have existing data or it's been a while
        const hasExistingData = savedReportsRef.current.length > 0;
        const shouldShowLoading = !hasExistingData || (Date.now() - lastDataLoad.current > 30000);
        
        if (shouldShowLoading) {
          setLoadingSavedReports(true);
        }
        
        const res = await api("/agents/reports/saved", {
          method: "GET",
          headers: { Accept: "application/json" },
          signal: controller.signal,
          nonCritical: true, // Don't sign out user if this API call fails
        });

        if (!res.ok) {
          const msg = await res.text().catch(() => "");
          console.error("Failed to load saved reports:", res.status, msg);
          // Only clear existing data if we don't have any or the call was expected to refresh
          if (!hasExistingData) {
            setSavedReports([]);
          }
          return;
        }

        const reports = await res.json();
        setSavedReports(reports);
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          console.error("Error loading saved reports:", err);
          // Only clear existing data if we don't have any
          if (savedReportsRef.current.length === 0) {
            setSavedReports([]);
          }
        }
      } finally {
        setLoadingSavedReports(false);
      }
    }

    loadPrebuiltAgents();
    loadCustomAgents();
    loadSavedReports();
    return () => {
      controller.abort();
      // Reset flag on cleanup to allow fresh calls if component remounts
      apiCallsInitiated.current = false;
    };
  }, [authLoading, session]);

  return (
    <div className="modern-dashboard">
      {/* Dashboard Header */}
      <header className="dashboard-header">
        <div className="header-container">
          <div className="header-left">
            <h1 className="dashboard-brand">Attenly</h1>
          </div>
          <div className="header-right">
            <div className="user-info">
              <span className="user-email">{session?.user?.email}</span>
            </div>
            <button
              className="email-settings-button"
              onClick={() => navigate('/settings')}
              title="Settings"
            >
              <span className="email-icon">⚙️</span>
              Settings
            </button>
            <button 
              className="logout-button"
              onClick={async () => {
                try {
                  await signOut();
                  navigate('/login');
                } catch (error) {
                  console.error('Logout failed:', error);
                }
              }}
            >
              <span className="logout-icon">🚪</span>
              Logout
            </button>
          </div>
        </div>
      </header>

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

          {/* Custom Agents Section */}
          <div className="custom-agents-section">
            <div className="section-header">
              <h2 className="section-title">
                <span className="section-icon">🛠️</span>
                My Custom Agents
              </h2>
              <p className="section-subtitle">
                Your personalized agents tailored to your specific needs
              </p>
                          <button 
                className="create-agent-button"
                onClick={() => navigate('/create-agent')}
              >
                <span className="button-icon">🤖</span>
                Create Custom Agent
              </button>
            </div>
            

            {loadingCustomAgents ? (
              <div className="loading-state">
                <p>Loading custom agents...</p>
              </div>
            ) : customAgents.length > 0 ? (
              <div className="custom-agents-grid">
                {customAgents.map((agent) => (
                  <CustomAgentCard
                    key={agent.id}
                    agent={agent}
                    onExecute={handleExecuteCustomAgent}
                    onDelete={handleDeleteCustomAgent}
                    onEdit={handleEditCustomAgent}
                  />
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <div className="empty-state-content">
                  <div className="empty-state-icon">🤖</div>
                  <h3 className="empty-state-title">No Custom Agents Yet</h3>
                  <p className="empty-state-description">
                    Create your first custom agent to get started with personalized document processing
                  </p>
                  <button 
                    className="create-agent-button"
                    onClick={() => navigate('/create-agent')}
                  >
                    <span className="button-icon">🤖</span>
                    Create Your First Agent
                  </button>
                </div>
              </div>
            )}
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
            ) : (
              <CompactReportList
                reports={savedReports}
                onView={handleViewSavedReport}
                onDelete={handleDeleteSavedReport}
                onDownload={handleDownloadSavedReport}
                onAudit={handleAuditSavedReport}
              />
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
