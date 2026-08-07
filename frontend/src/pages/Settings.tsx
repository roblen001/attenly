import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { api } from '../libs/https';
import type { EmailIngestSettings as EmailIngestSettingsType, Agent } from '../types';
import { useCredits } from '../hooks/useCredits';
import CreditOverview from '../components/settings/CreditOverview';
import VerifiedSendersList from '../components/email-ingest/VerifiedSendersList';
import UsageInstructions from '../components/email-ingest/UsageInstructions';
import { useAuth } from '../feature/auth/useAuth';
import './Settings.css';

type SettingsTab = 'credits' | 'email' | 'users';

type OrganizationUser = {
  id: string;
  email: string | null;
  display_name: string | null;
  role: string;
  status: string;
  last_login_at?: string | null;
  created_at?: string | null;
};

type VerificationNotice = {
  type: 'success' | 'error';
  message: string;
};

const verificationNotices: Record<string, VerificationNotice> = {
  success: {
    type: 'success',
    message: 'Email address verified. This sender can now submit documents to Attenly.',
  },
  invalid: {
    type: 'error',
    message: 'This verification link is invalid, expired, or already used. Request a new link from Verified Senders if needed.',
  },
  disabled: {
    type: 'error',
    message: 'Email ingest is disabled on this Attenly deployment.',
  },
  failed: {
    type: 'error',
    message: 'We could not verify this email address. Request a new verification link and try again.',
  },
};

const disabledEmailSettings = (
  message = 'Email ingest is disabled by server configuration.',
  provider = 'none'
): EmailIngestSettingsType => ({
  endpoint: null,
  delivery_address: null,
  delivery_mode: null,
  verified_senders: [],
  usage_summary: {
    jobs_last_24h: 0,
    rate_limit: 0,
  },
  enabled_by_config: false,
  provider,
  message,
});

export default function Settings() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { session, loading: authLoading } = useAuth();
  const isOidcAdmin = session?.user.user_metadata?.provider === 'oidc'
    && session?.user.app_metadata?.role === 'admin';
  const currentAppUserId = typeof session?.user.app_metadata?.app_user_id === 'string'
    ? session.user.app_metadata.app_user_id
    : null;

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
  const [verificationNotice, setVerificationNotice] = useState<VerificationNotice | null>(null);

  // Organization user administration state
  const [organizationUsers, setOrganizationUsers] = useState<OrganizationUser[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [usersError, setUsersError] = useState<string | null>(null);
  const [updatingUserId, setUpdatingUserId] = useState<string | null>(null);

  // Turn the public email-link callback into a clear in-app result, then remove
  // the callback parameter so refreshing the page does not repeat the message.
  useEffect(() => {
    const verificationResult = searchParams.get('sender_verification');
    if (!verificationResult) return;

    setActiveTab('email');
    setVerificationNotice(
      verificationNotices[verificationResult] || verificationNotices.failed
    );

    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('tab', 'email');
    nextParams.delete('sender_verification');
    setSearchParams(nextParams, { replace: true });
  }, [searchParams, setSearchParams]);

  // Update URL when tab changes
  const handleTabChange = (tab: SettingsTab) => {
    setActiveTab(tab);
    setSearchParams({ tab });
  };

  // A copied Users URL must not expose an admin view to other auth modes or roles.
  useEffect(() => {
    if (!authLoading && activeTab === 'users' && !isOidcAdmin) {
      setActiveTab('credits');
      setSearchParams({ tab: 'credits' }, { replace: true });
    }
  }, [activeTab, authLoading, isOidcAdmin, setSearchParams]);

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

  useEffect(() => {
    if (activeTab === 'users' && isOidcAdmin) {
      void fetchOrganizationUsers();
    }
  }, [activeTab, isOidcAdmin]);

  const fetchOrganizationUsers = async () => {
    try {
      setUsersLoading(true);
      setUsersError(null);
      const response = await api('/auth/api/auth/users', { method: 'GET' });
      const data = await response.json() as OrganizationUser[];
      setOrganizationUsers(data);
    } catch (err) {
      setUsersError(err instanceof Error ? err.message : 'Failed to load organization users');
    } finally {
      setUsersLoading(false);
    }
  };

  const handleUserStatusChange = async (user: OrganizationUser) => {
    const nextStatus = user.status === 'blocked' ? 'active' : 'blocked';
    const label = user.display_name || user.email || 'this user';
    const confirmationMessage = nextStatus === 'blocked'
      ? `Block ${label}? Their active Attenly sessions will be revoked immediately.`
      : `Unblock ${label}? They can sign in again if their identity-provider assignment and app role allow it.`;

    if (!window.confirm(confirmationMessage)) return;

    let reason: string | undefined;
    if (nextStatus === 'blocked') {
      const enteredReason = window.prompt('Optional reason for blocking this user:');
      if (enteredReason === null) return;
      reason = enteredReason.trim() || undefined;
    }

    try {
      setUpdatingUserId(user.id);
      setUsersError(null);
      const response = await api(`/auth/api/auth/users/${encodeURIComponent(user.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: nextStatus, ...(reason ? { reason } : {}) }),
      });
      const updated = await response.json() as OrganizationUser;
      setOrganizationUsers((current) => current.map((item) => (
        item.id === updated.id ? { ...item, ...updated } : item
      )));
    } catch (err) {
      setUsersError(err instanceof Error ? err.message : `Failed to ${nextStatus === 'blocked' ? 'block' : 'unblock'} user`);
    } finally {
      setUpdatingUserId(null);
    }
  };

  const fetchEmailSettings = async () => {
    try {
      setEmailLoading(true);
      setEmailError(null);
      const response = await api('/email-ingest/settings', { method: 'GET' });
      if (response.status === 503) {
        const data = await response.json().catch(() => null);
        setEmailSettings(disabledEmailSettings(data?.detail));
        return;
      }
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || 'Failed to fetch email ingest settings');
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
    if (emailSettings?.enabled_by_config === false) {
      setEmailError(emailSettings.message || 'Email ingest is disabled by server configuration.');
      return;
    }

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
    if (!window.confirm('Are you sure you want to disable email ingest? Your routing settings will be preserved but will not accept new emails.')) {
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
    const address = emailSettings?.delivery_address || emailSettings?.endpoint?.full_address;
    if (address) {
      navigator.clipboard.writeText(address);
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
  const hasEndpoint = Boolean(emailSettings?.endpoint);
  const isEmailAvailable = emailSettings?.enabled_by_config ?? true;
  const emailDisabledMessage = emailSettings?.message || 'Email ingest is disabled by server configuration.';
  const deliveryAddress = emailSettings?.delivery_address || emailSettings?.endpoint?.full_address || '';
  const usesGraphMailboxDelivery = emailSettings?.delivery_mode === 'graph_mailbox';

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
        {isOidcAdmin && (
          <button
            className={`settings-tab ${activeTab === 'users' ? 'active' : ''}`}
            onClick={() => handleTabChange('users')}
          >
            Users
          </button>
        )}
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
          {verificationNotice && (
            <div
              className={`verification-banner ${verificationNotice.type}`}
              role={verificationNotice.type === 'success' ? 'status' : 'alert'}
            >
              <span className="verification-icon">
                {verificationNotice.type === 'success' ? '\u2713' : '!'}
              </span>
              <span>{verificationNotice.message}</span>
              <button
                onClick={() => setVerificationNotice(null)}
                className="close-verification"
                aria-label="Dismiss verification message"
              >
                x
              </button>
            </div>
          )}

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
          ) : !isEmailAvailable ? (
            <div className="disabled-state">
              <div className="disabled-card">
                <div className="disabled-icon">@</div>
                <h2>Email Ingest Unavailable</h2>
                <p>{emailDisabledMessage}</p>
              </div>
            </div>
          ) : !hasEndpoint || !isEmailEnabled ? (
            <div className="disabled-state">
              <div className="disabled-card">
                <div className="disabled-icon">@</div>
                <h2>Email Ingest {hasEndpoint && !isEmailEnabled ? 'Disabled' : 'Not Enabled'}</h2>
                <p>
                  {hasEndpoint && !isEmailEnabled
                    ? 'Your email routing is currently disabled. Enable it to start receiving documents.'
                    : usesGraphMailboxDelivery
                      ? 'Enable email ingest to process attachments delivered to your configured Microsoft 365 mailbox.'
                      : 'Generate a unique email address to forward documents for automated processing.'}
                </p>
                {hasEndpoint && !isEmailEnabled && deliveryAddress && (
                  <div className="disabled-alias-info">
                    <p className="alias-label">
                      {usesGraphMailboxDelivery ? 'Microsoft 365 Mailbox:' : 'Your Email Alias:'}
                    </p>
                    <code>{deliveryAddress}</code>
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

              <UsageInstructions
                deliveryMode={emailSettings?.delivery_mode}
                deliveryAddress={deliveryAddress}
              />
            </div>
          ) : (
            <div className="enabled-state">
              {/* Email delivery card */}
              <div className="settings-card">
                <div className="card-header-section">
                  <h2>{usesGraphMailboxDelivery ? 'Report Intake Mailbox' : 'Your Email Alias'}</h2>
                  <button
                    onClick={handleDisable}
                    disabled={disabling}
                    className="btn btn-secondary btn-small"
                  >
                    {disabling ? 'Disabling...' : 'Disable'}
                  </button>
                </div>
                <div className="email-alias-display">
                  <code className="email-address">{deliveryAddress}</code>
                  <button
                    onClick={handleCopyEmail}
                    className={`btn btn-copy ${copySuccess ? 'copied' : ''}`}
                  >
                    {copySuccess ? 'Copied!' : 'Copy'}
                  </button>
                </div>
                <p className="help-text">
                  {usesGraphMailboxDelivery
                    ? 'Send attachments directly to this Microsoft 365 mailbox. Attenly monitors it through Microsoft Graph; no generated mailbox alias is required for this single-workspace deployment.'
                    : 'Forward emails with attachments to this address. Emails must come from verified senders.'}
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
              <UsageInstructions
                deliveryMode={emailSettings?.delivery_mode}
                deliveryAddress={deliveryAddress}
              />
            </div>
          )}
        </div>
      )}

      {/* Organization Users Tab — available only to OIDC organization admins. */}
      {activeTab === 'users' && isOidcAdmin && (
        <div className="settings-content">
          <div className="settings-card organization-users-card">
            <div className="organization-users-heading">
              <div>
                <h2>Organization Users</h2>
                <p className="help-text">
                  Manage access to this Attenly organization. Blocking a user revokes their active
                  Attenly sessions immediately. Identity-provider assignment and Attenly app
                  roles still determine who can sign in through SSO.
                </p>
              </div>
              <button
                type="button"
                className="btn btn-secondary btn-small"
                onClick={() => void fetchOrganizationUsers()}
                disabled={usersLoading || updatingUserId !== null}
              >
                {usersLoading ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>

            {usersError && (
              <div className="error-banner" role="alert">
                <span className="error-icon">!</span>
                <span>{usersError}</span>
                <button onClick={() => setUsersError(null)} className="close-error" aria-label="Dismiss error">x</button>
              </div>
            )}

            {usersLoading && organizationUsers.length === 0 ? (
              <div className="loading-state organization-users-loading">
                <div className="spinner"></div>
                <p>Loading organization users...</p>
              </div>
            ) : organizationUsers.length === 0 ? (
              <div className="organization-users-empty">
                <p>No organization users were found.</p>
                <button type="button" className="btn btn-primary" onClick={() => void fetchOrganizationUsers()}>
                  Retry
                </button>
              </div>
            ) : (
              <div className="organization-users-table-wrap">
                <table className="organization-users-table">
                  <thead>
                    <tr>
                      <th scope="col">User</th>
                      <th scope="col">Role</th>
                      <th scope="col">Status</th>
                      <th scope="col"><span className="visually-hidden">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {organizationUsers.map((user) => {
                      const isCurrentUser = user.id === currentAppUserId;
                      const isBlocked = user.status === 'blocked';
                      const isUpdating = updatingUserId === user.id;

                      return (
                        <tr key={user.id}>
                          <td>
                            <div className="organization-user-name">
                              {user.display_name || user.email || 'Unnamed user'}
                              {isCurrentUser && <span className="current-user-label">You</span>}
                            </div>
                            {user.email && user.email !== user.display_name && (
                              <div className="organization-user-email">{user.email}</div>
                            )}
                          </td>
                          <td>
                            <span className={`user-role-badge ${user.role}`}>{user.role}</span>
                          </td>
                          <td>
                            <span className={`user-status-badge ${isBlocked ? 'blocked' : 'active'}`}>
                              {isBlocked ? 'Blocked' : 'Active'}
                            </span>
                          </td>
                          <td className="organization-user-action">
                            {isCurrentUser ? (
                              <span className="current-account-text">Current account</span>
                            ) : (
                              <button
                                type="button"
                                className={`btn btn-small ${isBlocked ? 'btn-secondary' : 'btn-danger'}`}
                                onClick={() => void handleUserStatusChange(user)}
                                disabled={updatingUserId !== null}
                              >
                                {isUpdating ? 'Updating...' : isBlocked ? 'Unblock' : 'Block'}
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
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
