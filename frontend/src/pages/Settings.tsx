import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../libs/https';
import type { EmailIngestSettings as EmailIngestSettingsType, Agent } from '../types';
import { useCredits } from '../hooks/useCredits';
import CreditOverview from '../components/settings/CreditOverview';
import VerifiedSendersList from '../components/email-ingest/VerifiedSendersList';
import UsageInstructions from '../components/email-ingest/UsageInstructions';
import './Settings.css';

type SettingsTab = 'credits' | 'email';

export default function Settings() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Tab state from URL
  const initialTab = (searchParams.get('tab') as SettingsTab) || 'credits';
  const [activeTab, setActiveTab] = useState<SettingsTab>(initialTab);

  // Credits state (from hook)
  const { credits, usageSummary, loading: creditsLoading, error: creditsError, refreshCredits, fetchUsageSummary } = useCredits();

  // Email ingest state
  const [emailSettings, setEmailSettings] = useState<EmailIngestSettingsType | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [emailLoading, setEmailLoading] = useState(true);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [enabling, setEnabling] = useState(false);
  const [disabling, setDisabling] = useState(false);
  const [updatingAgent, setUpdatingAgent] = useState(false);
  const [copySuccess, setCopySuccess] = useState(false);

  // Update URL when tab changes
  const handleTabChange = (tab: SettingsTab) => {
    setActiveTab(tab);
    setSearchParams({ tab });
  };

  // Fetch email settings
  useEffect(() => {
    if (activeTab === 'email') {
      fetchEmailSettings();
      fetchAgents();
    }
  }, [activeTab]);

  // Fetch usage summary when on credits tab
  useEffect(() => {
    if (activeTab === 'credits' && credits) {
      fetchUsageSummary(30);
    }
  }, [activeTab, credits, fetchUsageSummary]);

  const fetchEmailSettings = async () => {
    try {
      setEmailLoading(true);
      setEmailError(null);
      const response = await api('/email-ingest/settings', { method: 'GET' });
      if (!response.ok) {
        throw new Error('Failed to fetch email ingest settings');
      }
      const data: EmailIngestSettingsType = await response.json();
      setEmailSettings(data);
    } catch (err) {
      setEmailError(err instanceof Error ? err.message : 'Failed to load settings');
    } finally {
      setEmailLoading(false);
    }
  };

  const fetchAgents = async () => {
    try {
      const [prebuiltResponse, customResponse] = await Promise.all([
        api('/agents/prebuilt', { method: 'GET' }),
        api('/agents/list_user_custom_agents', { method: 'GET' })
      ]);

      const prebuiltAgents: Agent[] = prebuiltResponse.ok ? await prebuiltResponse.json() : [];
      const customAgents: Agent[] = customResponse.ok ? await customResponse.json() : [];

      setAgents([...prebuiltAgents, ...customAgents]);
    } catch (err) {
      console.error('Failed to fetch agents:', err);
    }
  };

  const handleEnable = async () => {
    try {
      setEnabling(true);
      setEmailError(null);
      const response = await api('/email-ingest/enable', { method: 'POST' });
      if (!response.ok) {
        throw new Error('Failed to enable email ingest');
      }
      await fetchEmailSettings();
    } catch (err) {
      setEmailError(err instanceof Error ? err.message : 'Failed to enable email ingest');
    } finally {
      setEnabling(false);
    }
  };

  const handleDisable = async () => {
    if (!window.confirm('Are you sure you want to disable email ingest? Your email alias will be preserved but will not accept new emails.')) {
      return;
    }

    try {
      setDisabling(true);
      setEmailError(null);
      const response = await api('/email-ingest/disable', { method: 'POST' });
      if (!response.ok) {
        throw new Error('Failed to disable email ingest');
      }
      await fetchEmailSettings();
    } catch (err) {
      setEmailError(err instanceof Error ? err.message : 'Failed to disable email ingest');
    } finally {
      setDisabling(false);
    }
  };

  const handleCopyEmail = () => {
    if (emailSettings?.endpoint?.full_address) {
      navigator.clipboard.writeText(emailSettings.endpoint.full_address);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    }
  };

  const handleDefaultAgentChange = async (agentId: string) => {
    try {
      setUpdatingAgent(true);
      setEmailError(null);
      const response = await api('/email-ingest/default-agent', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId || null }),
      });
      if (!response.ok) {
        throw new Error('Failed to update default agent');
      }
      await fetchEmailSettings();
    } catch (err) {
      setEmailError(err instanceof Error ? err.message : 'Failed to update default agent');
    } finally {
      setUpdatingAgent(false);
    }
  };

  const isEmailEnabled = emailSettings?.endpoint?.is_active ?? false;
  const hasEndpoint = emailSettings?.endpoint !== null;

  return (
    <div className="settings-page">
      <div className="execution-header">
        <div className="header-content">
          <div className="header-left">
            <button onClick={() => navigate('/dashboard')} className="back-btn">
              <span className="back-icon">&#8592;</span>
              Back to Dashboard
            </button>
            <div className="agent-info">
              <div><h1 className="agent-title">Settings</h1></div>
              <div><p className="agent-description">Manage your account settings and usage</p></div>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="settings-tabs">
        <button
          className={`settings-tab ${activeTab === 'credits' ? 'active' : ''}`}
          onClick={() => handleTabChange('credits')}
        >
          Usage & Credits
        </button>
        <button
          className={`settings-tab ${activeTab === 'email' ? 'active' : ''}`}
          onClick={() => handleTabChange('email')}
        >
          Email Ingest
        </button>
      </div>

      {/* Credits Tab */}
      {activeTab === 'credits' && (
        <div className="settings-content">
          {creditsLoading ? (
            <div className="loading-state">
              <div className="spinner"></div>
              <p>Loading credits...</p>
            </div>
          ) : creditsError ? (
            <div className="error-state">
              <div className="error-icon">!</div>
              <h2>Failed to Load Credits</h2>
              <p>{creditsError}</p>
              <button onClick={refreshCredits} className="btn btn-primary">
                Retry
              </button>
            </div>
          ) : credits ? (
            <>
              <CreditOverview credits={credits} />

              {/* Usage Breakdown */}
              {usageSummary.length > 0 && (
                <div className="settings-card">
                  <h2>Usage Breakdown (Last 30 Days)</h2>
                  <div className="usage-breakdown">
                    {usageSummary.map((item) => (
                      <div key={item.operation_type} className="breakdown-item">
                        <span className="breakdown-label">
                          {formatOperationType(item.operation_type)}
                        </span>
                        <span className="breakdown-value">
                          {item.total_credits.toLocaleString()} credits
                        </span>
                        <span className="breakdown-requests">
                          ({item.request_count} requests)
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>
      )}

      {/* Email Ingest Tab */}
      {activeTab === 'email' && (
        <div className="settings-content">
          {emailError && (
            <div className="error-banner">
              <span className="error-icon">!</span>
              <span>{emailError}</span>
              <button onClick={() => setEmailError(null)} className="close-error">x</button>
            </div>
          )}

          {emailLoading ? (
            <div className="loading-state">
              <div className="spinner"></div>
              <p>Loading email settings...</p>
            </div>
          ) : !hasEndpoint || !isEmailEnabled ? (
            <div className="disabled-state">
              <div className="disabled-card">
                <div className="disabled-icon">@</div>
                <h2>Email Ingest {hasEndpoint && !isEmailEnabled ? 'Disabled' : 'Not Enabled'}</h2>
                <p>
                  {hasEndpoint && !isEmailEnabled
                    ? 'Your email alias exists but is currently disabled. Enable it to start receiving emails.'
                    : 'Generate a unique email address to forward documents for automated processing.'}
                </p>
                {hasEndpoint && !isEmailEnabled && emailSettings?.endpoint && (
                  <div className="disabled-alias-info">
                    <p className="alias-label">Your Email Alias:</p>
                    <code>{emailSettings.endpoint.full_address}</code>
                  </div>
                )}
                <button
                  onClick={handleEnable}
                  disabled={enabling}
                  className="btn btn-primary btn-large"
                >
                  {enabling ? 'Enabling...' : hasEndpoint ? 'Re-enable Email Ingest' : 'Enable Email Ingest'}
                </button>
              </div>

              <UsageInstructions />
            </div>
          ) : (
            <div className="enabled-state">
              {/* Email Alias Card */}
              <div className="settings-card">
                <div className="card-header-section">
                  <h2>Your Email Alias</h2>
                  <button
                    onClick={handleDisable}
                    disabled={disabling}
                    className="btn btn-secondary btn-small"
                  >
                    {disabling ? 'Disabling...' : 'Disable'}
                  </button>
                </div>
                <div className="email-alias-display">
                  <code className="email-address">{emailSettings?.endpoint?.full_address}</code>
                  <button
                    onClick={handleCopyEmail}
                    className={`btn btn-copy ${copySuccess ? 'copied' : ''}`}
                  >
                    {copySuccess ? 'Copied!' : 'Copy'}
                  </button>
                </div>
                <p className="help-text">
                  Forward emails with attachments to this address. Emails must come from verified senders.
                </p>
              </div>

              {/* Default Agent Card */}
              <div className="settings-card">
                <h2>Default Agent</h2>
                <p className="help-text">
                  Select which agent will process all documents sent via email.
                </p>
                <div className="agent-selector">
                  <select
                    value={emailSettings?.endpoint?.default_agent_id || ''}
                    onChange={(e) => handleDefaultAgentChange(e.target.value)}
                    disabled={updatingAgent || agents.length === 0}
                    className="agent-dropdown"
                  >
                    {!emailSettings?.endpoint?.default_agent_id && (
                      <option value="" disabled>
                        Select an agent...
                      </option>
                    )}
                    {agents.map((agent) => (
                      <option key={agent.id} value={agent.id}>
                        {agent.name}
                      </option>
                    ))}
                  </select>
                  {updatingAgent && <span className="updating-indicator">Updating...</span>}
                </div>
                {agents.length === 0 && (
                  <p className="help-text warning">
                    No agents available. Please create an agent first.
                  </p>
                )}
              </div>

              {/* Verified Senders */}
              <VerifiedSendersList
                senders={emailSettings?.verified_senders || []}
                onUpdate={fetchEmailSettings}
              />

              {/* Instructions */}
              <UsageInstructions />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Helper to format operation types for display
function formatOperationType(type: string): string {
  switch (type) {
    case 'llm_extraction':
      return 'Document Extraction';
    case 'llm_template':
      return 'Template Processing';
    case 'embedding_storage':
      return 'Document Embeddings';
    case 'embedding_search':
      return 'Search Queries';
    default:
      return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }
}
