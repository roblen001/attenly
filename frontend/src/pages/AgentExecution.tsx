import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import type { Agent, UploadedFile } from '../types';
import FileUpload from '../components/AgentExecution/FileUpload';
import { api } from '../libs/https';
import './AgentExecution.css';

export default function AgentExecutionPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [reportReady, setReportReady] = useState(false);

  useEffect(() => {
    const fetchAgent = async () => {
      if (!agentId) {
        setError('No agent ID provided');
        setLoading(false);
        return;
      }

      try {
        const response = await api(`/agents/${agentId}`);
        const agentData = await response.json();
        setAgent(agentData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load agent');
      } finally {
        setLoading(false);
      }
    };

    fetchAgent();
  }, [agentId]);

  const handleBack = () => {
    navigate('/dashboard');
  };

  const generateReport = async () => {
    if (uploadedFiles.length === 0) return;

    setIsGenerating(true);
    setReportReady(false);
    setError(null);

    try {
      // Call the new processing endpoint
      const response = await api(`/agents/${agentId}/process`, {
        method: 'POST'
      });

      if (!response.ok) {
        throw new Error(`Processing failed: ${response.statusText}`);
      }

      const result = await response.json();

      if (result.success) {
        setIsGenerating(false);
        setReportReady(true);
        console.log('Processing result:', result);
        // Backend will handle template population and return the complete report
      } else {
        throw new Error(result.error || 'Processing failed');
      }

    } catch (err) {
      console.error('Report generation failed:', err);
      setError(err instanceof Error ? err.message : 'Failed to generate report');
      setIsGenerating(false);
      setReportReady(false);
    }
  };

  const handlePreview = () => {
    // Placeholder for preview functionality
    console.log('Preview report clicked');
  };

  const downloadReportAsPDF = () => {
    // Placeholder for download functionality
    console.log('Download PDF clicked');
  };

  if (loading) {
    return (
      <div className="agent-execution-page" style={{ padding: '2rem', textAlign: 'center' }}>
        <div>Loading agent...</div>
      </div>
    );
  }

  if (error || !agent) {
    return (
      <div className="agent-execution-page" style={{ padding: '2rem', textAlign: 'center' }}>
        <div style={{ color: '#ef4444', marginBottom: '1rem' }}>
          {error || 'Agent not found'}
        </div>
        <button onClick={handleBack} className="btn btn-primary">
          Back to Dashboard
        </button>
      </div>
    );
  }

  return (
    <div className="agent-execution-page">
      <div className="execution-header">
        <div className="header-content">
          <div className="header-left">
            <button onClick={handleBack} className="back-btn">
              <span className="back-icon">←</span>
              Back to Dashboard
            </button>
            <div className="agent-info">
              <div><h1 className="agent-title">{agent.name}</h1></div>
              <div><p className="agent-description">{agent.description}</p></div>
            </div>
          </div>
          <div className="agent-stats">
            <div className="stat-item">
              <span className="stat-value">{agent.questions.length}</span>
              <span className="stat-label">Data Points</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="execution-main">
        <div className="execution-container">
          <div className="execution-grid">
            
            {/* File Upload Section */}
            <div className="upload-section">
              <div className="section-header">
                <h2 className="section-title">
                  <span className="section-icon">📁</span>
                  Upload Documents
                </h2>
              </div>
              <FileUpload
                files={uploadedFiles}
                onFilesChange={setUploadedFiles}
              />
            </div>

            {/* Generation Section */}
            <div className="generation-section">
              <div className="section-header">
                <h2 className="section-title">
                  <span className="section-icon">⚡</span>
                  Generate Report
                </h2>
              </div>

              <div className="generation-content">
                {!isGenerating && !reportReady && (
                  <div className="generation-ready">
                    <div className="ready-icon">🚀</div>
                    <h3>Ready to Generate</h3>
                    <p>Upload your documents and click generate to extract data using this agent's configuration.</p>
                    <button
                      onClick={generateReport}
                      disabled={uploadedFiles.length === 0}
                      className="generate-btn"
                    >
                      <span className="btn-icon">✨</span>
                      Generate Report
                    </button>
                  </div>
                )}

                {isGenerating && (
                  <div className="generation-progress">
                    <div className="progress-icon">⏳</div>
                    <h3>Generating Report...</h3>
                    <p>AI is analyzing your documents and extracting data points.</p>
                    <div className="progress-bar">
                      <div className="progress-fill"></div>
                    </div>
                  </div>
                )}

                {reportReady && (
                  <div className="generation-complete">
                    <div className="complete-icon">✅</div>
                    <h3>Report Generated!</h3>
                    <p>Your report has been successfully generated. You can preview and edit it, or download directly as PDF.</p>
                    <div className="report-actions">
                      <button onClick={handlePreview} className="preview-btn">
                        <span className="btn-icon">👁️</span>
                        Preview & Edit
                      </button>
                      <button onClick={downloadReportAsPDF} className="download-btn">
                        <span className="btn-icon">⬇️</span>
                        Download PDF
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
