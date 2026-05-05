import { useState, useEffect, useCallback, useRef } from 'react';
import { apiService } from '../services/api';
import { Tender, Page, Keyword, Stats, SystemStatus } from '../types';

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
  const [stats, setStats] = useState<Stats>({ total: 0, recommended: 0, lowMatch: 0, pages: 0 });
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({ status: 'unknown', message: '' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionPhase, setExtractionPhase] = useState<ExtractionPhase | null>(null);
  const [extractionPhaseLabel, setExtractionPhaseLabel] = useState('');
  const [extractionProgress, setExtractionProgress] = useState(0); // 0-100
  const phaseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  const loadPages = useCallback(async () => {
    try {
      const data = await apiService.getPages();
      setPages(data);
      setError(null);
    } catch (error) {
      console.error('Failed to load pages');
      setError('Failed to load pages');
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

  const updateStats = useCallback(() => {
    const recommendedCount = tenders.filter(t => t.passes_screening === true).length;
    const lowMatchCount = tenders.filter(t => t.passes_screening === false).length;
    setStats({
      total: tenders.length,
      recommended: recommendedCount,
      lowMatch: lowMatchCount,
      pages: pages.length
    });
  }, [tenders, pages]);

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
      // Also refresh tender count so the live counter updates
      loadTenders().catch(() => {});

      try {
        const status = await apiService.getExtractionStatus();
        if (!status.running) {
          // Backend finished — clean up
          _stopPhaseTimers();
          setExtractionProgress(100);
          setExtractionPhase(null);
          setExtractionPhaseLabel('');
          setIsExtracting(false);
          await Promise.all([loadTenders(), loadPages(), loadKeywords()]);
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
        await Promise.all([loadTenders(), loadPages(), loadKeywords()]);
      }
    }, 3_000);
  }, [isExtracting, loadTenders, loadPages, loadKeywords, _stopPhaseTimers, _runPhases]);

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
    setError,
    isExtracting,
    extractionPhase,
    extractionPhaseLabel,
    extractionProgress,
  };
};
