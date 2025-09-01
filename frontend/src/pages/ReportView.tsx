/**
 * ReportView Page Component
 * 
 * Main page component for displaying generated reports. Orchestrates all report-related
 * components and handles navigation between different states (loading, error, content).
 * Uses custom hooks for data management and state handling.
 */

import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import DocumentViewer from '../components/report/DocumentViewer';
import LoadingState from '../components/report/LoadingState';
import ErrorState from '../components/report/ErrorState';
import ReportHeader from '../components/report/ReportHeader';
import ReportActionsBar from '../components/report/ReportActionsBar';
import ReportInstructions from '../components/report/ReportInstructions';
import ReportContent from '../components/report/ReportContent';
import EditAnswerModal from '../components/report/EditAnswerModal';
import { useReportData } from '../hooks/useReportData';
import { useAnswerEditing } from '../hooks/useAnswerEditing';
import { useQuoteInteraction } from '../hooks/useQuoteInteraction';
import './ReportView.css';

export default function ReportView() {
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  
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

  // Navigate back to dashboard
  const handleBack = () => {
    navigate('/dashboard');
  };

  // Download PDF (placeholder implementation)
  const handleDownloadPDF = () => {
    // TODO: Implement actual PDF download
    console.log('Download PDF clicked - implementation pending');
    alert('PDF download functionality will be implemented in the next phase');
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
    </div>
  );
}
