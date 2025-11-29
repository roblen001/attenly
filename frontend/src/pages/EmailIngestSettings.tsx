import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../libs/https';
import type { EmailIngestSettings as EmailIngestSettingsType, Agent } from '../types';
import VerifiedSendersList from '../components/email-ingest/VerifiedSendersList';
import UsageInstructions from '../components/email-ingest/UsageInstructions';
import './EmailIngestSettings.css';

export default function EmailIngestSettings() {
  const navigate = useNavigate();
  
  const [settings, setSettings] = useState<EmailIngestSettingsType | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enabling, setEnabling] = useState(false);
  const [disabling, setDisabling] = useState(false);
  const [updatingAgent, setUpdatingAgent] = useState(false);
  const [copySuccess, setCopySuccess] = useState(false);

  useEffect(() => {
    fetchSettings();
    fetchAgents();
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await api('/email-ingest/settings', { method: 'GET' });
      if (!response.ok) {
        throw new Error('Failed to fetch email ingest settings');
      }
      const data: EmailIngestSettingsType = await response.json();
      setSettings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings');
    } finally {
      setLoading(false);
    }
  };

  const fetchAgents = async () => {
    try {
      // Fetch both prebuilt and custom agents for the default agent dropdown
      const [prebuiltResponse, customResponse] = await Promise.all([
        api('/agents/prebuilt', { method: 'GET' }),
        api('/agents/list_user_custom_agents', { method: 'GET' })
      ]);
      
      const prebuiltAgents: Agent[] = prebuiltResponse.ok ? await prebuiltResponse.json() : [];
      const customAgents: Agent[] = customResponse.ok ? await customResponse.json() : [];
      
      // Merge both lists (prebuilt first, then custom)
      setAgents([...prebuiltAgents, ...customAgents]);
    } catch (err) {
      console.error('Failed to fetch agents:', err);
    }
  };

  const handleEnable = async () => {
    try {
      setEnabling(true);
      setError(null);
      const response = await api('/email-ingest/enable', { method: 'POST' });
      if (!response.ok) {
        throw new Error('Failed to enable email ingest');
      }
      await fetchSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to enable email ingest');
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
      setError(null);
      const response = await api('/email-ingest/disable', { method: 'POST' });
      if (!response.ok) {
        throw new Error('Failed to disable email ingest');
      }
      await fetchSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to disable email ingest');
    } finally {
      setDisabling(false);
    }
  };

  const handleCopyEmail = () => {
    if (settings?.endpoint?.full_address) {
      navigator.clipboard.writeText(settings.endpoint.full_address);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    }
  };

  const handleDefaultAgentChange = async (agentId: string) => {
    try {
      setUpdatingAgent(true);
      setError(null);
      const response = await api('/email-ingest/default-agent', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId || null }),
      });
      if (!response.ok) {
        throw new Error('Failed to update default agent');
      }
      await fetchSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update default agent');
    } finally {
      setUpdatingAgent(false);
    }
  };

  if (loading) {
    return (
      <div className="email-ingest-settings">
        <div className="settings-header">
          <button onClick={() => navigate('/dashboard')} className="back-button">
            ← Back to Dashboard
          </button>
          <h1>Email to Attenly</h1>
        </div>
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading settings...</p>
        </div>
      </div>
    );
  }

  if (error && !settings) {
    return (
      <div className="email-ingest-settings">
        <div className="settings-header">
          <button onClick={() => navigate('/dashboard')} className="back-button">
            ← Back to Dashboard
          </button>
          <h1>Email to Attenly</h1>
        </div>
        <div className="error-state">
          <div className="error-icon">⚠️</div>
          <h2>Failed to Load Settings</h2>
          <p>{error}</p>
          <button onClick={fetchSettings} className="btn btn-primary">
            Retry
          </button>
        </div>
      </div>
    );
  }

  const isEnabled = settings?.endpoint?.is_active ?? false;
  const hasEndpoint = settings?.endpoint !== null;
  const jobsRemaining = settings ? settings.usage_summary.rate_limit - settings.usage_summary.jobs_last_24h : 0;

  return (
    <div className="email-ingest-settings">
      <div className="settings-header">
        <button onClick={() => navigate('/dashboard')} className="back-button">
          ← Back to Dashboard
        </button>
        <h1>Email to Attenly</h1>
        <p className="header-description">
          Forward emails with attachments to automatically generate reports
        </p>
      </div>

      {error && (
        <div className="error-banner">
          <span className="error-icon">⚠️</span>
          <span>{error}</span>
          <button onClick={() => setError(null)} className="close-error">✕</button>
        </div>
      )}

      {!hasEndpoint || !isEnabled ? (
        <div className="disabled-state">
          <div className="disabled-card">
            <div className="disabled-icon">📧</div>
            <h2>Email Ingest {hasEndpoint && !isEnabled ? 'Disabled' : 'Not Enabled'}</h2>
            <p>
              {hasEndpoint && !isEnabled
                ? 'Your email alias exists but is currently disabled. Enable it to start receiving emails.'
                : 'Generate a unique email address to forward documents for automated processing.'}
            </p>
            {hasEndpoint && !isEnabled && settings?.endpoint && (
              <div className="disabled-alias-info">
                <p className="alias-label">Your Email Alias:</p>
                <code>{settings.endpoint.full_address}</code>
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
              <code className="email-address">{settings?.endpoint?.full_address}</code>
              <button
                onClick={handleCopyEmail}
                className={`btn btn-copy ${copySuccess ? 'copied' : ''}`}
              >
                {copySuccess ? '✓ Copied!' : '📋 Copy'}
              </button>
            </div>
            <p className="help-text">
              Forward emails with attachments to this address. Emails must come from verified senders.
            </p>
          </div>

          {/* Usage Stats Card */}
          <div className="settings-card">
            <h2>Usage Statistics</h2>
            <div className="usage-stats">
              <div className="stat-item">
                <span className="stat-label">Jobs Last 24 Hours:</span>
                <span className="stat-value">{settings?.usage_summary.jobs_last_24h}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Rate Limit:</span>
                <span className="stat-value">{settings?.usage_summary.rate_limit} per day</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Jobs Remaining:</span>
                <span className={`stat-value ${jobsRemaining <= 5 ? 'low' : ''}`}>
                  {jobsRemaining}
                </span>
              </div>
            </div>
            {jobsRemaining <= 5 && (
              <div className="warning-message">
                ⚠️ You're approaching your daily rate limit.
              </div>
            )}
          </div>

          {/* Default Agent Card */}
          <div className="settings-card">
            <h2>Default Agent</h2>
            <p className="help-text">
              Select which agent will process all documents sent via email. All emailed documents will be processed using this agent.
            </p>
            <div className="agent-selector">
              <select
                value={settings?.endpoint?.default_agent_id || ''}
                onChange={(e) => handleDefaultAgentChange(e.target.value)}
                disabled={updatingAgent || agents.length === 0}
                className="agent-dropdown"
              >
                {!settings?.endpoint?.default_agent_id && (
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
                ⚠️ No agents available. Please create an agent first.
              </p>
            )}
          </div>

          {/* Verified Senders */}
          <VerifiedSendersList
            senders={settings?.verified_senders || []}
            onUpdate={fetchSettings}
          />

          {/* Instructions */}
          <UsageInstructions />
        </div>
      )}
    </div>
  );
}
