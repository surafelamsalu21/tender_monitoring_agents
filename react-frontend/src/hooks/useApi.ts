import { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/api';
import { Tender, Page, Keyword, Stats, SystemStatus } from '../types';

export const useApiData = () => {
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [pages, setPages] = useState<Page[]>([]);
  const [keywords, setKeywords] = useState<Keyword[]>([]);
  const [stats, setStats] = useState<Stats>({ total: 0, esg: 0, credit: 0, pages: 0 });
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({ status: 'unknown', message: '' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadTenders = useCallback(async () => {
    try {
      const data = await apiService.getTenders();
      setTenders(data);
    } catch (error) {
      console.error('Failed to load tenders');
      setError('Failed to load tenders');
    }
  }, []);

  const loadPages = useCallback(async () => {
    try {
      const data = await apiService.getPages();
      setPages(data);
    } catch (error) {
      console.error('Failed to load pages');
      setError('Failed to load pages');
    }
  }, []);

  const loadKeywords = useCallback(async () => {
    try {
      const data = await apiService.getKeywords();
      setKeywords(data);
    } catch (error) {
      console.error('Failed to load keywords');
      setError('Failed to load keywords');
    }
  }, []);

  const checkSystemStatus = useCallback(async () => {
    try {
      const status = await apiService.checkHealth();
      setSystemStatus(status);
    } catch (error) {
      setSystemStatus({ status: 'error', message: 'Backend not available' });
    }
  }, []);

  const updateStats = useCallback(() => {
    const esgCount = tenders.filter(t => t.category === 'esg').length;
    const creditCount = tenders.filter(t => t.category === 'credit_rating').length;
    setStats({
      total: tenders.length,
      esg: esgCount,
      credit: creditCount,
      pages: pages.length
    });
  }, [tenders, pages]);

  const triggerExtraction = useCallback(async () => {
    try {
      await apiService.triggerExtraction();
      // Reload data after extraction
      await Promise.all([loadTenders(), loadPages(), loadKeywords()]);
    } catch (error) {
      console.error('Failed to trigger extraction');
      setError('Failed to trigger extraction');
    }
  }, [loadTenders, loadPages, loadKeywords]);

  useEffect(() => {
    const initializeApp = async () => {
      setLoading(true);
      await checkSystemStatus();
      await Promise.all([loadTenders(), loadPages(), loadKeywords()]);
      setLoading(false);
    };
    initializeApp();
  }, [checkSystemStatus, loadTenders, loadPages, loadKeywords]);

  useEffect(() => {
    updateStats();
  }, [updateStats]);

  return {
    tenders,
    pages,
    keywords,
    stats,
    systemStatus,
    loading,
    error,
    loadTenders,
    loadPages,
    loadKeywords,
    triggerExtraction,
    setError
  };
};
