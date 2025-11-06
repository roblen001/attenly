/**
 * useReportData Hook
 * 
 * Custom hook for managing report data fetching and state management.
 * Handles loading states, error handling, and authentication checks
 * when fetching report data from the API. Supports both current and saved reports.
 * 
 * @param params - Object containing either agentId (for current reports) or reportId (for saved reports)
 * @returns Object containing reportData, setReportData, loading, error states, and report type info
 */

import { useState, useEffect } from 'react';
import type { ReportData } from '../types';
import { api } from '../libs/https';
import { useAuth } from '../feature/auth/useAuth';

interface UseReportDataParams {
  agentId?: string;
  reportId?: string;
}

export const useReportData = (params: UseReportDataParams) => {
  const { loading: authLoading, session } = useAuth();
  const [reportData, setReportData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reportType, setReportType] = useState<'current' | 'saved' | null>(null);
  const [reportInfo, setReportInfo] = useState<{ id: string; name: string } | null>(null);
  const [preloadStatus, setPreloadStatus] = useState<'idle' | 'loading' | 'complete' | 'error'>('idle');

  useEffect(() => {
    const fetchReportData = async () => {
      const { agentId, reportId } = params;
      
      if (!agentId && !reportId) {
        setError('No agent ID or report ID provided');
        setLoading(false);
        return;
      }

      // Wait for auth to be ready AND session to exist before making API calls
      if (authLoading || !session) {
        return;
      }

      try {
        let response;
        let result;
        
        if (reportId) {
          // Fetch saved report
          setReportType('saved');
          response = await api(`/agents/reports/saved/${reportId}`);
          
          if (!response.ok) {
            throw new Error(`Failed to fetch saved report: ${response.statusText}`);
          }
          
          result = await response.json();
          setReportData(result.report_data);
          setReportInfo({ id: result.id, name: result.report_name });
          
          // Auto-preload PDFs for fast quote viewing (waits before hiding loading)
          await preloadDocuments(reportId);
          
        } else if (agentId) {
          // Fetch current report
          setReportType('current');
          response = await api(`/agents/${agentId}/report`);
          
          if (!response.ok) {
            throw new Error(`Failed to fetch report: ${response.statusText}`);
          }
          
          result = await response.json();
          
          if (result.success) {
            setReportData(result.report_data);
            setReportInfo({ id: result.agent_id, name: result.agent_name });
          } else {
            throw new Error(result.error || 'Failed to generate report');
          }
        }
        
      } catch (err) {
        if (err instanceof Error && err.message.includes('Authentication failed')) {
          // Auth error will be handled by the api() function (redirect to login)
          return;
        }
        setError(err instanceof Error ? err.message : 'Failed to load report');
      } finally {
        setLoading(false);
      }
    };

    fetchReportData();
  }, [params.agentId, params.reportId, authLoading, session]);

  // Preload documents for saved reports
  const preloadDocuments = async (reportId: string) => {
    try {
      setPreloadStatus('loading');
      console.log(`[Preload] Starting PDF preload for report ${reportId}...`);
      
      const response = await api(`/agents/reports/saved/${reportId}/preload-documents`, {
        method: 'POST',
      });
      
      if (!response.ok) {
        throw new Error('Failed to preload documents');
      }
      
      const result = await response.json();
      console.log(`[Preload] Successfully preloaded ${result.documents_loaded} PDFs (${result.total_size_mb} MB)`);
      setPreloadStatus('complete');
      
    } catch (err) {
      console.warn('[Preload] Failed to preload documents:', err);
      // Don't fail the report loading if preload fails - quotes will just be slower
      setPreloadStatus('error');
    }
  };

  // Cleanup: Unload preloaded documents when component unmounts (for saved reports)
  useEffect(() => {
    return () => {
      if (reportType === 'saved' && params.reportId && preloadStatus === 'complete') {
        // Cleanup preloaded documents from memory
        api(`/agents/reports/saved/${params.reportId}/unload-documents`, {
          method: 'DELETE',
        }).catch(() => {
          // Ignore errors - this is just cleanup
        });
      }
    };
  }, [reportType, params.reportId, preloadStatus]);

  return {
    reportData,
    setReportData,
    loading,
    error,
    reportType,
    reportInfo,
    preloadStatus
  };
};
