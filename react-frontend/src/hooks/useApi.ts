import { useState, useEffect, useCallback, useRef } from 'react';
import { apiService } from '../services/api';
import { Tender, Page, Keyword, Stats, SystemStatus } from '../types';
import { getLocalDayUtcBounds } from '../utils/tenderDates';

export type ExtractionPhase =
  | 'crawling'
  | 'screening'
  | 'details'
  | 'email'
  | 'finishing';

const PHASE_SEQUENCE: { phase: ExtractionPhase; label: string; durationMs: number }[] = [
  { phase: 'crawling',   label: 'Crawling monitored pages…',            durationMs: 12_000 },
  { phase: 'screening',  label: 'Agent 1: Screening tenders…',          durationMs: 20_000 },
  { phase: 'details',    label: 'Agent 2: Extracting tender details…',   durationMs: 35_000 },
  { phase: 'email',      label: 'Agent 3: Composing email notifications…', durationMs: 18_000 },
  { phase: 'finishing',  label: 'Finishing up…',                         durationMs: 99_999 },
];

export const useApiData = () => {
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [pages, setPages] = useState<Page[]>([]);
  const [keywords, setKeywords] = useState<Keyword[]>([]);
  const [stats, setStats] = useState<Stats>({
    total: 0,
    recommended: 0,
    lowMatch: 0,
    pages: 0,
    addedToday: 0,
    addedTodayRecommended: 0,
    addedTodayLowMatch: 0,
  });
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({ status: 'unknown', message: '' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionPhase, setExtractionPhase] = useState<ExtractionPhase | null>(null);
  const [extractionPhaseLabel, setExtractionPhaseLabel] = useState('');
  const [extractionProgress, setExtractionProgress] = useState(0); // 0-100
  const phaseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pagesLenRef = useRef(0);

  const loadTenders = useCallback(async () => {
    try {
      const data = await apiService.getTenders();
      setTenders(data);
      setError(null);
    } catch (error) {
      console.error('Failed to load tenders');
      setError('Failed to load tenders');
    }
  }, []);

  const loadPages = useCallback(async (): Promise<number> => {
    try {
      const data = await apiService.getPages();
      setPages(data);
      pagesLenRef.current = data.length;
      setError(null);
      return data.length;
    } catch (error) {
      console.error('Failed to load pages');
      setError('Failed to load pages');
      return 0;
    }
  }, []);

  const loadKeywords = useCallback(async () => {
    try {
      const data = await apiService.getKeywords();
      setKeywords(data);
      setError(null);
    } catch (error) {
      console.error('Failed to load keywords');
      setError('Failed to load keywords');
    }
  }, []);

  const checkSystemStatus = useCallback(async () => {
    try {
      const status = await apiService.checkHealth();
      setSystemStatus(status);
      setError(null);
    } catch (error) {
      setSystemStatus({ status: 'error', message: 'Backend not available' });
    }
  }, []);

  const refreshStats = useCallback(async (pagesCount: number) => {
    try {
      const bounds = getLocalDayUtcBounds();
      const data = await apiService.getTenderStatsSummary(bounds);
      setStats({
        total: data.total_tenders,
        recommended: data.recommended_screening,
        lowMatch: data.low_match_screening,
        pages: pagesCount,
        addedToday: data.tenders_added_today ?? 0,
        addedTodayRecommended: data.tenders_added_today_recommended ?? 0,
        addedTodayLowMatch: data.tenders_added_today_low_match ?? 0,
      });
    } catch (e) {
      console.error('Failed to load tender stats', e);
    }
  }, []);

  const _stopPhaseTimers = useCallback(() => {
    if (phaseTimerRef.current) clearTimeout(phaseTimerRef.current);
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    phaseTimerRef.current = null;
    pollTimerRef.current = null;
  }, []);

  const _runPhases = useCallback(() => {
    let phaseIdx = 0;
    let elapsed = 0;

    const totalMs = PHASE_SEQUENCE.reduce((s, p) => s + p.durationMs, 0) - 99_999 + 1;

    const advance = () => {
      if (phaseIdx >= PHASE_SEQUENCE.length) return;
      const { phase, label, durationMs } = PHASE_SEQUENCE[phaseIdx];
      setExtractionPhase(phase);
      setExtractionPhaseLabel(label);
      // rough progress: each phase spans a fraction of total (excluding last open-ended phase)
      const knownTotal = PHASE_SEQUENCE.slice(0, -1).reduce((s, p) => s + p.durationMs, 0);
      const knownElapsed = PHASE_SEQUENCE.slice(0, phaseIdx).reduce((s, p) => s + p.durationMs, 0);
      setExtractionProgress(Math.min(90, Math.round((knownElapsed / knownTotal) * 90)));

      phaseIdx++;
      if (phaseIdx < PHASE_SEQUENCE.length) {
        phaseTimerRef.current = setTimeout(advance, durationMs);
      }
    };

    advance();
  }, []);

  const triggerExtraction = useCallback(async () => {
    if (isExtracting) return;

    // Fire the trigger (returns immediately — backend runs in background)
    try {
      await apiService.triggerExtraction();
    } catch (error) {
      console.error('Failed to trigger extraction');
      setError('Failed to trigger extraction');
      return;
    }

    setIsExtracting(true);
    setExtractionProgress(0);
    _stopPhaseTimers();
    _runPhases();

    // Poll /extraction-status every 3 s; stop when backend reports done
    const MAX_WAIT_MS = 10 * 60 * 1000; // 10-minute hard cap
    const started = Date.now();

    pollTimerRef.current = setInterval(async () => {
      // Also refresh tender list + today's count from DB while the job runs
      loadTenders().catch(() => {});
      refreshStats(pagesLenRef.current).catch(() => {});

      try {
        const status = await apiService.getExtractionStatus();
        if (!status.running) {
          // Backend finished — clean up
          _stopPhaseTimers();
          setExtractionProgress(100);
          setExtractionPhase(null);
          setExtractionPhaseLabel('');
          setIsExtracting(false);
          const plen = await loadPages();
          await Promise.all([loadTenders(), loadKeywords()]);
          await refreshStats(plen);
        }
      } catch {
        // Ignore transient network errors
      }

      // Hard cap: stop after MAX_WAIT_MS regardless
      if (Date.now() - started > MAX_WAIT_MS) {
        _stopPhaseTimers();
        setExtractionPhase(null);
        setExtractionPhaseLabel('');
        setIsExtracting(false);
        const plen = await loadPages();
        await Promise.all([loadTenders(), loadKeywords()]);
        await refreshStats(plen);
      }
    }, 3_000);
  }, [isExtracting, loadTenders, loadPages, loadKeywords, _stopPhaseTimers, _runPhases, refreshStats]);

  useEffect(() => {
    const initializeApp = async () => {
      setLoading(true);
      await checkSystemStatus();
      const plen = await loadPages();
      await Promise.all([loadTenders(), loadKeywords()]);
      await refreshStats(plen);
      setLoading(false);
    };
    initializeApp();
  }, [checkSystemStatus, loadTenders, loadPages, loadKeywords, refreshStats]);

  // Refresh "added today" stats when the browser's local calendar day rolls over
  useEffect(() => {
    let lastKey = new Date().toDateString();
    const id = window.setInterval(() => {
      const key = new Date().toDateString();
      if (key !== lastKey) {
        lastKey = key;
        refreshStats(pagesLenRef.current).catch(() => {});
      }
    }, 30_000);
    return () => window.clearInterval(id);
  }, [refreshStats]);

  const refreshTenderStats = useCallback(async () => {
    await refreshStats(pagesLenRef.current);
  }, [refreshStats]);

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
    refreshTenderStats,
    triggerExtraction,
    setError,
    isExtracting,
    extractionPhase,
    extractionPhaseLabel,
    extractionProgress,
  };
};
