import React, { useState, useMemo } from 'react';
import './CompactReportList.css';

interface SavedReport {
  id: string;
  report_name: string;
  agent_name: string;
  agent_id: string;
  saved_at: string;
  generated_at: string;
}

interface CompactReportListProps {
  reports: SavedReport[];
  onView: (reportId: string) => void;
  onDelete: (reportId: string) => void;
  onDownload: (reportId: string) => void;
  onAudit: (reportId: string) => void;
}

export default function CompactReportList({ reports, onView, onDelete, onDownload, onAudit }: CompactReportListProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const handleView = (e: React.MouseEvent, report: SavedReport) => {
    e.stopPropagation();
    onView(report.id);
  };

  const handleDownload = async (e: React.MouseEvent, report: SavedReport) => {
    e.stopPropagation();
    onDownload(report.id);
  };

  const handleDelete = async (e: React.MouseEvent, report: SavedReport) => {
    e.stopPropagation();
    
    const confirmMessage = `Are you sure you want to delete "${report.report_name}"? This action cannot be undone.`;
    if (!window.confirm(confirmMessage)) {
      return;
    }

    onDelete(report.id);
  };

  const handleAudit = (e: React.MouseEvent, report: SavedReport) => {
    e.stopPropagation();
    onAudit(report.id);
  };

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const filteredReports = useMemo(() => {
    const sortedReports = [...reports].sort((a, b) => new Date(b.saved_at).getTime() - new Date(a.saved_at).getTime());
    
    if (!searchQuery.trim()) {
      // Show only the 5 most recent reports when no search query
      return sortedReports.slice(0, 5);
    }
    
    // When searching, show all matching results
    const query = searchQuery.toLowerCase().trim();
    return sortedReports.filter(report => 
      report.report_name.toLowerCase().includes(query)
    );
  }, [reports, searchQuery]);

  return (
    <div className="compact-report-list">
      <div className="search-container">
        <div className="search-input-wrapper">
          <input
            type="text"
            placeholder="Search reports by name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="search-input"
          />
        </div>
      </div>

      <div className="reports-scrollable">
        {filteredReports.length === 0 ? (
          <div className="no-reports-found">
            {searchQuery ? (
              <>
                <span className="no-results-icon">🔍</span>
                <p>No reports found matching "{searchQuery}"</p>
                <button 
                  onClick={() => setSearchQuery('')}
                  className="clear-search-link"
                >
                  Clear search to see recent reports
                </button>
              </>
            ) : (
              <>
                <span className="empty-icon">📄</span>
                <p>No reports generated yet</p>
              </>
            )}
          </div>
        ) : (
          <div className="compact-reports-list">
            {filteredReports.map((report) => (
              <div
                key={report.id}
                className="compact-report-item"
                onClick={(e) => handleView(e, report)}
              >
                <div className="report-main-info">
                  <div className="report-name-section">
                    <span className="report-icon">📊</span>
                    <span className="report-name">
                      {report.report_name}
                    </span>
                  </div>
                  <div className="report-meta">
                    <span className="report-agent">{report.agent_name}</span>
                    <span className="report-date">{formatDate(report.saved_at)}</span>
                  </div>
                </div>
                <div className="report-actions">
                  <button
                    onClick={(e) => handleView(e, report)}
                    className="btn btn-small btn-secondary"
                    title="View report"
                  >
                    <span className="btn-icon">👁️</span>
                  </button>
                  <button
                    onClick={(e) => handleAudit(e, report)}
                    className="btn btn-small btn-secondary"
                    title="View audit trail"
                  >
                    <span className="btn-icon">📋</span>
                  </button>
                  <button
                    onClick={(e) => handleDownload(e, report)}
                    className="btn btn-small btn-primary"
                    title="Download PDF"
                  >
                    <span className="btn-icon">⬇️</span>
                  </button>
                  <button
                    onClick={(e) => handleDelete(e, report)}
                    className="btn btn-small btn-danger"
                    title="Delete report"
                  >
                    <span className="btn-icon">🗑️</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {!searchQuery && reports.length > 5 && (
        <div className="reports-footer">
          <p className="footer-hint">
            Showing {Math.min(5, reports.length)} of {reports.length} reports. 
            Use search to find older reports.
          </p>
        </div>
      )}
    </div>
  );
}
