/**
 * useReportData Hook
 * 
 * Custom hook for managing report data fetching and state management.
 * Handles loading states, error handling, and authentication checks
 * when fetching report data from the API.
 * 
 * @param agentId - The ID of the agent to fetch report data for
 * @returns Object containing reportData, setReportData, loading, and error states
 */

import { useState, useEffect } from 'react';
import type { ReportData } from '../types';
import { api } from '../libs/https';
import { useAuth } from '../feature/auth/useAuth';

export const useReportData = (agentId: string | undefined) => {
  const { loading: authLoading } = useAuth();
  const [reportData, setReportData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchReportData = async () => {
      if (!agentId) {
        setError('No agent ID provided');
        setLoading(false);
        return;
      }

      // Wait for auth to be ready before making API calls
      if (authLoading) {
        return;
      }

      try {
        const response = await api(`/agents/${agentId}/report`);
        
        if (!response.ok) {
          throw new Error(`Failed to fetch report: ${response.statusText}`);
        }
        
        const result = await response.json();
        
        if (result.success) {
          setReportData(result.report_data);
        } else {
          throw new Error(result.error || 'Failed to generate report');
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
  }, [agentId, authLoading]);

  return {
    reportData,
    setReportData,
    loading,
    error
  };
};
