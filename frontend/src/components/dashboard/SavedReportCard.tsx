import React from 'react';
import './SavedReportCard.css';

interface SavedReport {
  id: string;
  report_name: string;
  agent_name: string;
  agent_id: string;
  saved_at: string;
  generated_at: string;
}

interface SavedReportCardProps {
  report: SavedReport;
  onDelete: (id: string) => void;
  onDownload: (id: string) => void;
  onClick: () => void;
}

export default function SavedReportCard({ report, onDelete, onDownload, onClick }: SavedReportCardProps) {
  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click
    if (window.confirm(`Are you sure you want to delete "${report.report_name}"?`)) {
      onDelete(report.id);
    }
  };

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click
    onDownload(report.id);
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="saved-report-card" onClick={onClick}>
      <div className="card-header">
        <div className="report-info">
          <h3 className="report-name">{report.report_name}</h3>
          <p className="agent-name">📊 {report.agent_name}</p>
        </div>
        <div className="card-actions">
          <button
            onClick={handleDownload}
            className="action-btn download-btn"
            title="Download PDF"
          >
            ⬇️
          </button>
          <button
            onClick={handleDelete}
            className="action-btn delete-btn"
            title="Delete Report"
          >
            🗑️
          </button>
        </div>
      </div>
      
      <div className="card-footer">
        <div className="date-info">
          <span className="saved-date">
            💾 Saved: {formatDate(report.saved_at)}
          </span>
          <span className="generated-date">
            ⚡ Generated: {formatDate(report.generated_at)}
          </span>
        </div>
      </div>
    </div>
  );
}
