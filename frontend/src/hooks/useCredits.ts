/**
 * useCredits Hook
 *
 * Custom hook for managing user credit status and usage data.
 * Fetches credit status from the API and provides refresh functionality.
 */

import { useState, useEffect, useCallback } from 'react';
import type { CreditStatus, UsageSummaryItem, UsageHistoryItem } from '../types';
import { api } from '../libs/https';
import { useAuth } from '../feature/auth/useAuth';

interface UseCreditsReturn {
  credits: CreditStatus | null;
  usageSummary: UsageSummaryItem[];
  usageHistory: UsageHistoryItem[];
  loading: boolean;
  error: string | null;
  refreshCredits: () => Promise<void>;
  fetchUsageSummary: (days?: number) => Promise<void>;
  fetchUsageHistory: (days?: number) => Promise<void>;
}

export function useCredits(): UseCreditsReturn {
  const { loading: authLoading, session } = useAuth();
  const [credits, setCredits] = useState<CreditStatus | null>(null);
  const [usageSummary, setUsageSummary] = useState<UsageSummaryItem[]>([]);
  const [usageHistory, setUsageHistory] = useState<UsageHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCredits = useCallback(async () => {
    if (!session) return;

    try {
      setLoading(true);
      setError(null);

      const response = await api('/api/credits', { method: 'GET' });

      if (!response.ok) {
        throw new Error('Failed to fetch credit status');
      }

      const data: CreditStatus = await response.json();
      setCredits(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load credits');
    } finally {
      setLoading(false);
    }
  }, [session]);

  const fetchUsageSummary = useCallback(async (days: number = 30) => {
    if (!session) return;

    try {
      const response = await api(`/api/credits/usage?days=${days}`, { method: 'GET' });

      if (!response.ok) {
        throw new Error('Failed to fetch usage summary');
      }

      const data: UsageSummaryItem[] = await response.json();
      setUsageSummary(data);
    } catch (err) {
      console.error('Failed to fetch usage summary:', err);
    }
  }, [session]);

  const fetchUsageHistory = useCallback(async (days: number = 30) => {
    if (!session) return;

    try {
      const response = await api(`/api/credits/history?days=${days}`, { method: 'GET' });

      if (!response.ok) {
        throw new Error('Failed to fetch usage history');
      }

      const data: UsageHistoryItem[] = await response.json();
      setUsageHistory(data);
    } catch (err) {
      console.error('Failed to fetch usage history:', err);
    }
  }, [session]);

  const refreshCredits = useCallback(async () => {
    await fetchCredits();
  }, [fetchCredits]);

  // Initial fetch when auth is ready
  useEffect(() => {
    if (!authLoading && session) {
      fetchCredits();
    }
  }, [authLoading, session, fetchCredits]);

  return {
    credits,
    usageSummary,
    usageHistory,
    loading: loading || authLoading,
    error,
    refreshCredits,
    fetchUsageSummary,
    fetchUsageHistory
  };
}

// Helper function to get warning level color
export function getWarningLevelColor(level: string): string {
  switch (level) {
    case 'blocked':
      return '#ef4444'; // red
    case 'critical':
      return '#ef4444'; // red
    case 'warning':
      return '#eab308'; // yellow
    default:
      return '#22c55e'; // green
  }
}

// Helper function to format credits for display
export function formatCredits(credits: number): string {
  return credits.toLocaleString();
}

// Helper function to get progress bar color based on percentage
export function getProgressColor(percentage: number): string {
  if (percentage >= 90) return '#ef4444'; // red
  if (percentage >= 70) return '#eab308'; // yellow
  return '#22c55e'; // green
}
