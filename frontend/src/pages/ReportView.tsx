/**
 * ReportView Page Component
 * 
 * Main page component for displaying generated reports. Orchestrates all report-related
 * components and handles navigation between different states (loading, error, content).
 * Uses custom hooks for data management and state handling.
 */

import { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation, useSearchParams } from 'react-router';
import DocumentViewer from '../components/report/DocumentViewer';
import LoadingState from '../components/report/LoadingState';
import ErrorState from '../components/report/ErrorState';
import ReportHeader from '../components/report/ReportHeader';
import ReportActionsBar from '../components/report/ReportActionsBar';
import ReportInstructions from '../components/report/ReportInstructions';
import ReportContent from '../components/report/ReportContent';
import EditAnswerModal from '../components/report/EditAnswerModal';
import DownloadModal from '../components/report/DownloadModal';
import SaveReportModal from '../components/report/SaveReportModal';
import { useReportData } from '../hooks/useReportData';
import { useAnswerEditing } from '../hooks/useAnswerEditing';
import { useQuoteInteraction } from '../hooks/useQuoteInteraction';
import { api } from '../libs/https';
import type { ReportViewMode, AuditChange } from '../types';
import './ReportView.css';

export default function ReportView() {
  const { agentId, reportId } = useParams<{ agentId?: string; reportId?: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  // Determine report type first (needed for view mode calculation)
  const isSavedReport = location.pathname.includes('/report/saved/');

  // Determine view mode from query parameter
  const mode: ReportViewMode = searchParams.get('mode') === 'audit' ? 'audit' : 'normal';
  const isAuditMode = mode === 'audit';

  // Determine actual view mode for ReportContent component
  // - Normal mode (current OR saved reports) = editable with green boxes
  // - Audit mode = audit trail view with track changes
  const viewMode: 'editable' | 'readonly' | 'audit' = isAuditMode ? 'audit' : 'editable';

  // Audit trail state
  const [auditChanges, setAuditChanges] = useState<Record<string, AuditChange[]>>({});
  const [hasChanges, setHasChanges] = useState(false);

  // Determine report parameters
  const reportParams = isSavedReport ? { reportId } : { agentId };

  // Modal state
  const [showDownloadModal, setShowDownloadModal] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Custom hooks for data and state management
  const { reportData, setReportData, loading, error, reportType } = useReportData(reportParams);
  const {
    editingAnswer,
    editedAnswerText,
    setEditedAnswerText,
    handleEditAnswer,
    handleSaveAnswer,
    handleCancelEdit
  } = useAnswerEditing(reportData, setReportData);
  const {
    selectedQuote,
    showDocumentViewer,
    handleQuoteClick,
    handleCloseDocumentViewer
  } = useQuoteInteraction(reportData);

  // Fetch audit trail data when in audit mode
  useEffect(() => {
    if (isAuditMode && isSavedReport && reportId && !loading) {
      const fetchAuditData = async () => {
        try {
          const response = await api(`/agents/reports/saved/${reportId}/with-audit`);
          if (response.ok) {
            const data = await response.json();
            setAuditChanges(data.changes || {});
            setHasChanges(data.has_changes || false);
          }
        } catch (err) {
          console.error('Failed to fetch audit data:', err);
        }
      };
      fetchAuditData();
    }
  }, [isAuditMode, isSavedReport, reportId, loading]);

  // Clear report cache when user leaves the page (only for current reports)
  useEffect(() => {
    const handleBeforeUnload = () => {
      // Only clear cache for current reports, not saved reports
      if (reportType === 'current' && agentId) {
        // Use sendBeacon for reliable cleanup during page unload
        const url = `/agents/reports/${agentId}/cache`;
        if (navigator.sendBeacon) {
          navigator.sendBeacon(`${window.location.origin}/api${url}`, JSON.stringify({ method: 'DELETE' }));
        } else {
          // Fallback for browsers without sendBeacon
          api(url, { method: 'DELETE' }).catch(() => {});
        }
      }
    };

    // Add event listener for page unload
    window.addEventListener('beforeunload', handleBeforeUnload);

    // Cleanup event listener on component unmount
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [reportType, agentId]);

  // Navigate back to dashboard
  const handleBack = () => {
    // Clear cache when explicitly navigating back (only for current reports)
    if (reportType === 'current' && agentId) {
      api(`/agents/reports/${agentId}/cache`, { method: 'DELETE' })
        .catch(err => console.warn('Cache cleanup failed:', err));
    }
    navigate('/dashboard');
  };

  // Toggle between normal and audit modes for saved reports
  const handleToggleAuditMode = () => {
    if (!isSavedReport || !reportId) return;
    
    const newMode = isAuditMode ? 'normal' : 'audit';
    navigate(`/report/saved/${reportId}?mode=${newMode}`);
  };

  // Show download modal
  const handleDownloadPDF = () => {
    setShowDownloadModal(true);
  };

  // Handle download with references
  const handleDownloadWithReferences = async () => {
    setIsDownloading(true);
    try {
      let response;
      if (reportType === 'saved' && reportId) {
        response = await api(`/agents/reports/saved/${reportId}/pdf?with_references=true`);
      } else if (reportType === 'current' && agentId) {
        response = await api(`/agents/${agentId}/pdf?with_references=true`);
      } else {
        throw new Error('Invalid report configuration');
      }

      // Create blob and download
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;

      // Get filename from response headers
      const contentDisposition = response.headers.get('content-disposition');
      let filename = 'report_with_references.pdf';
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
      console.error('Download failed:', error);
      alert('Download failed. Please try again.');
    } finally {
      setIsDownloading(false);
      setShowDownloadModal(false);
    }
  };

  // Handle download without references
  const handleDownloadWithoutReferences = async () => {
    setIsDownloading(true);
    try {
      let response;
      if (reportType === 'saved' && reportId) {
        response = await api(`/agents/reports/saved/${reportId}/pdf?with_references=false`);
      } else if (reportType === 'current' && agentId) {
        response = await api(`/agents/${agentId}/pdf?with_references=false`);
      } else {
        throw new Error('Invalid report configuration');
      }

      // Create blob and download
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;

      // Get filename from response headers
      const contentDisposition = response.headers.get('content-disposition');
      let filename = 'report.pdf';
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
      console.error('Download failed:', error);
      alert('Download failed. Please try again.');
    } finally {
      setIsDownloading(false);
      setShowDownloadModal(false);
    }
  };

  // Close download modal
  const handleCloseDownloadModal = () => {
    if (!isDownloading) {
      setShowDownloadModal(false);
    }
  };

  // Save action for both current and saved reports
  const handleSaveReport = async () => {
    try {
      if (reportType === 'saved' && reportId) {
        // Persist edits directly to the saved report
        setIsSaving(true);
        if (!reportData) {
          throw new Error('No report data to save');
        }
        const response = await api(`/agents/reports/saved/${reportId}`, {
          method: 'PATCH',
          body: JSON.stringify({ report_data: reportData }),
        });
        if (!response.ok) {
          throw new Error('Failed to update saved report');
        }
        alert('Saved changes to report successfully!');
      } else if (reportType === 'current') {
        // Open naming modal for saving a new report
        setShowSaveModal(true);
      } else {
        alert('Invalid report configuration. Cannot save.');
      }
    } catch (error) {
      console.error('Save failed:', error);
      alert(error instanceof Error ? error.message : 'Failed to save changes');
    } finally {
      setIsSaving(false);
    }
  };

  // Handle save report (only for current reports) - persist edits to cache first
  const handleSaveReportSubmit = async (reportName: string) => {
    if (reportType !== 'current' || !agentId) return;
    
    setIsSaving(true);
    try {
      if (!reportData) {
        throw new Error('No report data to save');
      }

      // First, update the cached report with the latest edited data
      const cacheUpdate = await api(`/agents/reports/${agentId}/cache`, {
        method: 'PUT',
        body: JSON.stringify({ report_data: reportData }),
      });
      if (!cacheUpdate.ok) {
        throw new Error('Failed to update cached report before saving');
      }

      // Then, save the cached report to Supabase with the provided name
      const response = await api(`/agents/${agentId}/reports/save`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ report_name: reportName }),
      });

      if (!response.ok) {
        throw new Error('Failed to save report');
      }

      await response.json();
      
      // Show success message (you could add a toast notification here)
      alert(`Report "${reportName}" saved successfully!`);
      
    } catch (error) {
      console.error('Save failed:', error);
      throw error; // Re-throw to let the modal handle the error
    } finally {
      setIsSaving(false);
    }
  };

  // Close save modal
  const handleCloseSaveModal = () => {
    if (!isSaving) {
      setShowSaveModal(false);
    }
  };

  // Show loading state
  if (loading) {
    return <LoadingState />;
  }

  // Show error state
  if (error || !reportData) {
    return <ErrorState error={error || 'Report data not available'} onBack={handleBack} />;
  }

  // Show document viewer if quote is selected
  if (showDocumentViewer && selectedQuote) {
    return (
      <DocumentViewer
        quote={selectedQuote}
        onClose={handleCloseDocumentViewer}
        reportType={reportType || 'current'}
        reportId={reportId}
        agentId={agentId}
      />
    );
  }

  // Main report view
  return (
    <div className="report-view-page">
      <ReportHeader reportData={reportData} onBack={handleBack} />
      
      <ReportActionsBar 
        onDownloadPDF={handleDownloadPDF} 
        onSaveReport={handleSaveReport}
        showSaveButton={reportType === 'current' || (isSavedReport && !isAuditMode)}
        viewMode={mode}
        onToggleAuditMode={isSavedReport ? handleToggleAuditMode : undefined}
      />

      <div className="report-main">
        <div className="report-container">
          {!isAuditMode && <ReportInstructions />}
          {isAuditMode && hasChanges && (
            <div className="audit-mode-banner">
              <span className="audit-badge">📋 Audit Trail Mode</span>
              <p className="audit-legend">
                <span className="legend-item"><span className="audit-trail-insert-sample">Green highlight</span> = Human added text</span>
                {' · '}
                <span className="legend-item"><span className="audit-trail-delete-sample">Red strikethrough</span> = Human deleted text</span>
              </p>
            </div>
          )}
          {isAuditMode && !hasChanges && (
            <div className="audit-mode-banner no-changes">
              <span className="audit-badge">📋 Audit Trail Mode</span>
              <p>No changes detected - this report matches the original AI-generated content.</p>
            </div>
          )}
          <ReportContent 
            reportData={reportData}
            onAnswerEdit={handleEditAnswer}
            onQuoteClick={handleQuoteClick}
            viewMode={viewMode}
            auditChanges={auditChanges}
          />
        </div>
      </div>

      <EditAnswerModal
        editingAnswer={editingAnswer}
        editedAnswerText={editedAnswerText}
        setEditedAnswerText={setEditedAnswerText}
        onSave={handleSaveAnswer}
        onCancel={handleCancelEdit}
      />

      <DownloadModal
        isOpen={showDownloadModal}
        onClose={handleCloseDownloadModal}
        onDownloadWithReferences={handleDownloadWithReferences}
        onDownloadWithoutReferences={handleDownloadWithoutReferences}
        isDownloading={isDownloading}
      />

      <SaveReportModal
        isOpen={showSaveModal}
        onClose={handleCloseSaveModal}
        onSave={handleSaveReportSubmit}
        isSaving={isSaving}
      />
    </div>
  );
}
