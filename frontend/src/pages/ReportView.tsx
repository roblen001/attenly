/**
 * ReportView Page Component
 * 
 * Main page component for displaying generated reports. Orchestrates all report-related
 * components and handles navigation between different states (loading, error, content).
 * Uses custom hooks for data management and state handling.
 */

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import DocumentViewer from '../components/report/DocumentViewer';
import LoadingState from '../components/report/LoadingState';
import ErrorState from '../components/report/ErrorState';
import ReportHeader from '../components/report/ReportHeader';
import ReportActionsBar from '../components/report/ReportActionsBar';
import ReportInstructions from '../components/report/ReportInstructions';
import ReportContent from '../components/report/ReportContent';
import EditAnswerModal from '../components/report/EditAnswerModal';
import DownloadModal from '../components/report/DownloadModal';
import { useReportData } from '../hooks/useReportData';
import { useAnswerEditing } from '../hooks/useAnswerEditing';
import { useQuoteInteraction } from '../hooks/useQuoteInteraction';
import { api } from '../libs/https';
import './ReportView.css';

export default function ReportView() {
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();

  // Modal state
  const [showDownloadModal, setShowDownloadModal] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  // Custom hooks for data and state management
  const { reportData, setReportData, loading, error } = useReportData(agentId);
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

  // Clear report cache when user leaves the page (tab close, refresh, or navigation away)
  useEffect(() => {
    const handleBeforeUnload = () => {
      // This runs when user closes tab, refreshes, or navigates away from the site
      if (agentId) {
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
  }, [agentId]);

  // Navigate back to dashboard
  const handleBack = () => {
    // Clear cache when explicitly navigating back
    if (agentId) {
      api(`/agents/reports/${agentId}/cache`, { method: 'DELETE' })
        .catch(err => console.warn('Cache cleanup failed:', err));
    }
    navigate('/dashboard');
  };

  // Show download modal
  const handleDownloadPDF = () => {
    setShowDownloadModal(true);
  };

  // Handle download with references
  const handleDownloadWithReferences = async () => {
    setIsDownloading(true);
    try {
      const response = await api(`/agents/${agentId}/pdf?with_references=true`);

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
      const response = await api(`/agents/${agentId}/pdf?with_references=false`);

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
      />
    );
  }

  // Main report view
  return (
    <div className="report-view-page">
      <ReportHeader reportData={reportData} onBack={handleBack} />
      
      <ReportActionsBar onDownloadPDF={handleDownloadPDF} />

      <div className="report-main">
        <div className="report-container">
          <ReportInstructions />
          <ReportContent 
            reportData={reportData}
            onAnswerEdit={handleEditAnswer}
            onQuoteClick={handleQuoteClick}
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
    </div>
  );
}
