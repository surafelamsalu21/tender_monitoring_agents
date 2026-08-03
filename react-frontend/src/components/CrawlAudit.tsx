import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock3, RefreshCw, Search, ShieldAlert } from 'lucide-react';
import { apiService, CrawlAuditPage, CrawlAuditReport } from '../services/api';

interface CrawlAuditProps {
  isAdmin: boolean;
}

type HealthFilter = 'all' | 'issues' | 'healthy' | 'failing' | 'overdue' | 'never_crawled';

const HEALTH_BADGE: Record<string, string> = {
  healthy: 'bg-green-100 text-green-800 border-green-200',
  failing: 'bg-red-100 text-red-800 border-red-200',
  overdue: 'bg-amber-100 text-amber-800 border-amber-200',
  never_crawled: 'bg-slate-100 text-slate-800 border-slate-200',
  attention: 'bg-orange-100 text-orange-800 border-orange-200',
};

const HEALTH_LABEL: Record<string, string> = {
  healthy: 'Healthy',
  failing: 'Failing',
  overdue: 'Overdue',
  never_crawled: 'Never Crawled',
  attention: 'Needs Attention',
};

const formatDateTime = (value?: string | null): string => {
  if (!value) return '—';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return '—';
  return dt.toLocaleString();
};

const formatAgo = (value?: string | null): string => {
  if (!value) return 'never';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return 'unknown';
  const diffMs = Date.now() - dt.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
};

export const CrawlAudit: React.FC<CrawlAuditProps> = ({ isAdmin }) => {
  const [report, setReport] = useState<CrawlAuditReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [healthFilter, setHealthFilter] = useState<HealthFilter>('issues');
  const [windowHours, setWindowHours] = useState(72);
  const [scheduleLabel, setScheduleLabel] = useState<string>('Loading schedule...');

  const loadReport = async (hours: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiService.getCrawlAuditReport(hours);
      setReport(data);
    } catch (err: any) {
      const message = err?.response?.data?.detail || err?.message || 'Failed to load crawl audit';
      setError(String(message));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isAdmin) return;
    loadReport(windowHours);
  }, [isAdmin]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!isAdmin) return;
    let mounted = true;
    let lastRunAt: string | null = null;
    let previousInProgress = false;

    const refreshScheduleAndAutoSync = async () => {
      try {
        const status = await apiService.getSchedulerStatus();
        if (!mounted) return;
        setScheduleLabel(status?.schedule_description || 'Schedule unavailable');

        const currentLastRun = status?.last_run_at || null;
        const currentInProgress = Boolean(status?.in_progress);

        // Refresh audit right after any extraction cycle completes.
        const justFinished = previousInProgress && !currentInProgress;
        const lastRunChanged = Boolean(currentLastRun && currentLastRun !== lastRunAt);
        if (justFinished || lastRunChanged) {
          loadReport(windowHours);
        }

        previousInProgress = currentInProgress;
        lastRunAt = currentLastRun;
      } catch {
        if (mounted) setScheduleLabel('Schedule unavailable');
      }
    };

    refreshScheduleAndAutoSync();
    const timer = window.setInterval(refreshScheduleAndAutoSync, 15000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [isAdmin, windowHours]); // eslint-disable-line react-hooks/exhaustive-deps

  const filteredRows = useMemo(() => {
    const rows = report?.pages || [];
    return rows.filter((row) => {
      const q = query.trim().toLowerCase();
      const matchesQuery =
        !q ||
        row.page_name.toLowerCase().includes(q) ||
        row.url.toLowerCase().includes(q) ||
        String(row.page_id).includes(q);
      if (!matchesQuery) return false;

      if (healthFilter === 'all') return true;
      if (healthFilter === 'issues') return row.health !== 'healthy';
      return row.health === healthFilter;
    });
  }, [report, query, healthFilter]);

  if (!isAdmin) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
        <div className="flex items-center gap-3 text-amber-700">
          <ShieldAlert className="h-6 w-6" />
          <div>
            <p className="font-semibold">Admin access required</p>
            <p className="text-sm text-amber-600">
              Crawl audit visibility is restricted to admin and super admin users.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Crawl Audit</h1>
          <p className="text-sm text-gray-600 mt-1">
            Verify every monitored page is being crawled and quickly spot failures.
          </p>
        </div>
        <button
          onClick={() => loadReport(windowHours)}
          disabled={loading}
          className="inline-flex items-center px-4 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-60"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="h-4 w-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by page name, URL, or ID"
              className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-red-200 focus:border-red-300"
            />
          </div>
          <select
            value={healthFilter}
            onChange={(e) => setHealthFilter(e.target.value as HealthFilter)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          >
            <option value="issues">Show issues only</option>
            <option value="all">All pages</option>
            <option value="healthy">Healthy</option>
            <option value="failing">Failing</option>
            <option value="overdue">Overdue</option>
            <option value="never_crawled">Never crawled</option>
          </select>
          <select
            value={windowHours}
            onChange={(e) => {
              const next = Number(e.target.value || 48);
              setWindowHours(next);
              loadReport(next);
            }}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          >
            <option value={24}>Last 24h window</option>
            <option value={72}>Last 72h window</option>
            <option value={96}>Last 96h window</option>
            <option value={168}>Last 7 days window</option>
          </select>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-gray-600">
            Scheduler: <span className="font-medium">{scheduleLabel}</span>. Audit auto-syncs after completed runs (manual or scheduled).
          </p>
          <p className="text-xs text-gray-500">Polling every 15s for run completion</p>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4">
          {error}
        </div>
      )}

      {report && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-sm text-gray-600">Coverage</p>
            <p className="text-2xl font-bold text-gray-900">{report.summary.coverage_percent}%</p>
            <p className="text-xs text-gray-500 mt-1">
              {report.summary.recently_crawled_pages}/{report.summary.total_active_pages} pages crawled recently
            </p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-sm text-gray-600">Pages Needing Attention</p>
            <p className="text-2xl font-bold text-red-700">
              {report.summary.not_recently_crawled_pages + report.summary.recent_failed_pages}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              Not recent: {report.summary.not_recently_crawled_pages} · Failed: {report.summary.recent_failed_pages}
            </p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-sm text-gray-600">Due But Not Crawled</p>
            <p className="text-2xl font-bold text-amber-700">
              {report.summary.due_now_not_recently_crawled_pages}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              Due now: {report.summary.due_now_pages}
            </p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-sm text-gray-600">Never Crawled</p>
            <p className="text-2xl font-bold text-slate-700">{report.summary.never_crawled_pages}</p>
            <p className="text-xs text-gray-500 mt-1">
              Generated {formatAgo(report.generated_at)} · window {report.recent_window_hours}h
            </p>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Page Crawl Details</h2>
          <p className="text-xs text-gray-500">{filteredRows.length} row(s)</p>
        </div>

        {loading ? (
          <div className="p-10 text-center text-gray-500">
            <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2" />
            Loading crawl audit...
          </div>
        ) : filteredRows.length === 0 ? (
          <div className="p-10 text-center text-gray-500">No pages match this filter.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="text-left px-4 py-3 font-medium">Page</th>
                  <th className="text-left px-4 py-3 font-medium">Health</th>
                  <th className="text-left px-4 py-3 font-medium">Last Crawl</th>
                  <th className="text-left px-4 py-3 font-medium">Latest Result</th>
                  <th className="text-left px-4 py-3 font-medium">Useful Signals</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row: CrawlAuditPage) => (
                  <tr key={row.page_id} className="border-t border-gray-100 align-top">
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900">{row.page_name}</p>
                      <p className="text-xs text-gray-500 break-all">{row.url}</p>
                      <p className="text-xs text-gray-500 mt-1">
                        ID {row.page_id} · {row.crawl_strategy} · every {row.crawl_frequency_hours}h
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs font-medium ${HEALTH_BADGE[row.health] || HEALTH_BADGE.attention}`}>
                        {row.health === 'healthy' ? (
                          <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
                        ) : (
                          <AlertTriangle className="h-3.5 w-3.5 mr-1" />
                        )}
                        {HEALTH_LABEL[row.health] || row.health}
                      </span>
                      <p className="text-xs text-gray-500 mt-2">
                        Due now: {row.is_due_now ? 'Yes' : 'No'}
                      </p>
                      <p className="text-xs text-gray-500">
                        Consecutive failures: {row.consecutive_failures}
                      </p>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-700">
                      <p><span className="font-medium">Started:</span> {formatDateTime(row.latest_log?.started_at || row.last_crawled)}</p>
                      <p><span className="font-medium">Success:</span> {formatDateTime(row.last_successful_crawl)}</p>
                      <p className="text-gray-500 mt-1">{formatAgo(row.latest_log?.started_at || row.last_crawled)}</p>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-700">
                      <p className="font-medium">{row.latest_log?.status || 'no log yet'}</p>
                      <p>Tenders found: {row.latest_log?.tenders_found ?? 0}</p>
                      <p>New tenders: {row.latest_log?.tenders_new ?? 0}</p>
                      {row.latest_log?.error_message && (
                        <p className="text-red-700 mt-1 max-w-[360px] break-words">
                          Error: {row.latest_log.error_message}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-700">
                      <div className="flex items-center gap-2">
                        <Clock3 className="h-3.5 w-3.5 text-gray-400" />
                        Recent crawl: {row.has_recent_crawl ? 'Yes' : 'No'}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <CheckCircle2 className="h-3.5 w-3.5 text-gray-400" />
                        Recent success: {row.has_recent_success ? 'Yes' : 'No'}
                      </div>
                      {row.health !== 'healthy' && (
                        <p className="text-amber-700 mt-2">
                          Action: check page config/strategy and re-run extraction.
                        </p>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
