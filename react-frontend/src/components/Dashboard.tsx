// components/Dashboard.tsx - Enhanced with processing information
import React, { useState } from 'react';
import { 
  FileText, Leaf, CreditCard, Globe, Play, AlertCircle, 
  Bot, Cpu, Database, Clock, Loader2, Globe2, Search, Mail, CheckCircle2, X
} from 'lucide-react';
import { StatCard } from './StatCard';
import { Stats, SystemStatus, Tender } from '../types';
import { ExtractionPhase } from '../hooks/useApi';
import { isTenderCreatedLocalToday } from '../utils/tenderDates';

interface DashboardProps {
  stats: Stats;
  systemStatus: SystemStatus;
  tenders: Tender[];
  onTriggerExtraction: () => void;
  isExtracting?: boolean;
  extractionPhase?: ExtractionPhase | null;
  extractionPhaseLabel?: string;
  extractionProgress?: number;
}

const PHASE_ICONS: Record<string, React.ReactNode> = {
  crawling:  <Globe2   className="h-5 w-5" />,
  screening: <Search   className="h-5 w-5" />,
  details:   <Cpu      className="h-5 w-5" />,
  email:     <Mail     className="h-5 w-5" />,
  finishing: <CheckCircle2 className="h-5 w-5" />,
};

const PHASE_STEPS: { key: ExtractionPhase; label: string }[] = [
  { key: 'crawling',  label: 'Crawl' },
  { key: 'screening', label: 'Screen' },
  { key: 'details',   label: 'Details' },
  { key: 'email',     label: 'Email' },
  { key: 'finishing', label: 'Done' },
];

export const Dashboard: React.FC<DashboardProps> = ({
  stats,
  systemStatus,
  tenders,
  onTriggerExtraction,
  isExtracting = false,
  extractionPhase = null,
  extractionPhaseLabel = '',
  extractionProgress = 0,
}) => {
  const [progressDismissed, setProgressDismissed] = useState(false);

  // Re-show the panel automatically when a new extraction starts
  const prevExtracting = React.useRef(false);
  React.useEffect(() => {
    if (isExtracting && !prevExtracting.current) {
      setProgressDismissed(false);
    }
    prevExtracting.current = isExtracting;
  }, [isExtracting]);

  const showProgress = (isExtracting || extractionProgress === 100) && !progressDismissed;
  // Calculate processing statistics
  const processedTenders = tenders.filter(t => t.is_processed);
  const unprocessedTenders = tenders.filter(t => !t.is_processed);
  const notifiedTenders = tenders.filter(t => t.is_notified);
  const unnotifiedTenders = tenders.filter(t => !t.is_notified);
  
  // Today's tenders (local calendar day — resets at midnight; matches DB stats)
  const todaysTenders = tenders
    .filter((t) => isTenderCreatedLocalToday(t.created_at))
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="space-y-8">
      {/* System Status */}
      <div className={`p-6 rounded-xl border-2 ${
        systemStatus.status === 'healthy' 
          ? 'bg-green-50 border-green-200 text-green-800' 
          : 'bg-red-50 border-red-200 text-red-800'
      }`}>
        <div className="flex items-center">
          <AlertCircle className="h-6 w-6 mr-3" />
          <span className="font-semibold text-lg">System Status: {systemStatus.status}</span>
        </div>
        <p className="text-base mt-2 ml-9">{systemStatus.message}</p>
      </div>

      {/* Main Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-8">
        <StatCard
          title="Total Tenders"
          value={stats.total}
          icon={FileText}
          color="bg-primary-500"
          trend={
            stats.addedToday === 1
              ? '1 added today'
              : `${stats.addedToday} added today`
          }
          trendClassName={
            stats.addedToday > 0 ? 'text-emerald-600' : 'text-gray-500'
          }
        />
        <StatCard
          title="Recommended match"
          value={stats.recommended}
          icon={Leaf}
          color="bg-green-500"
          trend={`${Math.round((stats.recommended / stats.total * 100) || 0)}% of total · ${
            stats.addedTodayRecommended === 1
              ? '1 new today'
              : `${stats.addedTodayRecommended} new today`
          }`}
          trendClassName={
            stats.addedTodayRecommended > 0 ? 'text-emerald-600' : 'text-gray-500'
          }
        />
        <StatCard
          title="Low match (1–2 criteria)"
          value={stats.lowMatch}
          icon={CreditCard}
          color="bg-amber-500"
          trend={`${Math.round((stats.lowMatch / stats.total * 100) || 0)}% of total · ${
            stats.addedTodayLowMatch === 1
              ? '1 new today'
              : `${stats.addedTodayLowMatch} new today`
          }`}
          trendClassName={
            stats.addedTodayLowMatch > 0 ? 'text-amber-700' : 'text-gray-500'
          }
        />
        <StatCard
          title="Active Pages"
          value={stats.pages}
          icon={Globe}
          color="bg-orange-500"
        />
      </div>

      {/* AI Processing Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Agent 1 (Extracted)</p>
              <p className="text-2xl font-bold text-primary-600 mt-1">{stats.total}</p>
              <p className="text-xs text-gray-500 mt-1">Basic tender info</p>
            </div>
            <div className="p-3 rounded-full bg-primary-500">
              <Bot className="h-6 w-6 text-white" />
            </div>
          </div>
        </div>
        
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Agent 2 (Processed)</p>
              <p className="text-2xl font-bold text-green-600 mt-1">{processedTenders.length}</p>
              <p className="text-xs text-gray-500 mt-1">Detailed analysis done</p>
            </div>
            <div className="p-3 rounded-full bg-green-500">
              <Cpu className="h-6 w-6 text-white" />
            </div>
          </div>
        </div>
        
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Agent 3 (Notified)</p>
              <p className="text-2xl font-bold text-primary-600 mt-1">{notifiedTenders.length}</p>
              <p className="text-xs text-gray-500 mt-1">Email notifications sent</p>
            </div>
            <div className="p-3 rounded-full bg-primary-500">
              <Database className="h-6 w-6 text-white" />
            </div>
          </div>
        </div>
      </div>

      {/* Processing Pipeline Status */}
      <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-8">
        <h3 className="text-xl font-semibold text-gray-900 mb-6">AI Processing Pipeline</h3>
        
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-4">
            <div className="flex items-center">
              <div className="w-4 h-4 bg-primary-500 rounded-full mr-2"></div>
              <span className="text-sm text-gray-600">Agent 1: Extract & Categorize</span>
            </div>
            <div className="flex items-center">
              <div className="w-4 h-4 bg-green-500 rounded-full mr-2"></div>
              <span className="text-sm text-gray-600">Agent 2: Detail Extraction</span>
            </div>
            <div className="flex items-center">
              <div className="w-4 h-4 bg-primary-500 rounded-full mr-2"></div>
              <span className="text-sm text-gray-600">Agent 3: Email Composition</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h4 className="font-medium text-gray-800 mb-3">Processing Status</h4>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Processed by Agent 2</span>
                <span className="font-medium text-green-600">{processedTenders.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Pending Processing</span>
                <span className="font-medium text-orange-600">{unprocessedTenders.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Email Notifications Sent</span>
                <span className="font-medium text-primary-600">{notifiedTenders.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Pending Notifications</span>
                <span className="font-medium text-primary-600">{unnotifiedTenders.length}</span>
              </div>
            </div>
          </div>
          
          <div>
            <h4 className="font-medium text-gray-800 mb-3">Success Rate</h4>
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span>Agent 2 Processing</span>
                  <span>{Math.round((processedTenders.length / stats.total * 100) || 0)}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div 
                    className="bg-green-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${(processedTenders.length / stats.total * 100) || 0}%` }}
                  ></div>
                </div>
              </div>
              
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span>Email Notifications</span>
                  <span>{Math.round((notifiedTenders.length / stats.total * 100) || 0)}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div 
                    className="bg-primary-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${(notifiedTenders.length / stats.total * 100) || 0}%` }}
                  ></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Quick Actions + Live Extraction Progress */}
      <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-8">
        <h3 className="text-xl font-semibold text-gray-900 mb-6">Quick Actions</h3>
        <div className="flex flex-wrap gap-4 mb-6">
          <button
            onClick={onTriggerExtraction}
            disabled={isExtracting}
            className={`flex items-center px-6 py-3 rounded-lg font-medium text-base transition-all ${
              isExtracting
                ? 'bg-primary-400 text-white cursor-not-allowed opacity-80'
                : 'bg-primary-600 text-white hover:bg-primary-700'
            }`}
          >
            {isExtracting ? (
              <Loader2 className="h-5 w-5 mr-3 animate-spin" />
            ) : (
              <Play className="h-5 w-5 mr-3" />
            )}
            {isExtracting ? 'Extraction Running…' : 'Trigger Manual Extraction'}
          </button>
        </div>

        {/* Live progress panel */}
        {showProgress && (
          <div className="mt-2 rounded-xl border border-primary-200 bg-primary-50 p-6 space-y-5">
            {/* Header */}
            <div className="flex items-start gap-3">
              {isExtracting ? (
                <Loader2 className="h-6 w-6 text-primary-600 animate-spin shrink-0 mt-0.5" />
              ) : (
                <CheckCircle2 className="h-6 w-6 text-green-500 shrink-0 mt-0.5" />
              )}
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-primary-800 text-base">
                  {isExtracting
                    ? (extractionPhaseLabel || 'Starting extraction…')
                    : 'Extraction complete!'}
                </p>
                <p className="text-xs text-primary-500 mt-0.5">
                  {isExtracting
                    ? 'This may take 1–3 minutes depending on how many pages are monitored.'
                    : `${stats.total} tender${stats.total !== 1 ? 's' : ''} found. You can close this panel.`}
                </p>
              </div>
              <button
                onClick={() => setProgressDismissed(true)}
                className="shrink-0 p-1 rounded-md text-primary-400 hover:text-primary-700 hover:bg-primary-100 transition-colors"
                title="Dismiss"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Indeterminate + determinate progress bar */}
            <div className="relative w-full h-3 bg-primary-100 rounded-full overflow-hidden">
              {/* Shimmer layer (always active) */}
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/40 to-transparent animate-shimmer rounded-full" />
              {/* Filled layer */}
              <div
                className="h-full bg-gradient-to-r from-primary-500 to-primary-400 rounded-full transition-all duration-700"
                style={{ width: `${Math.max(4, extractionProgress)}%` }}
              />
            </div>

            {/* Step indicators */}
            <div className="flex items-center justify-between gap-1">
              {PHASE_STEPS.map((step, idx) => {
                const phaseOrder = PHASE_STEPS.findIndex(s => s.key === extractionPhase);
                const isDone    = phaseOrder > idx;
                const isActive  = phaseOrder === idx;
                return (
                  <div key={step.key} className="flex flex-col items-center gap-1 flex-1">
                    <div
                      className={`flex items-center justify-center w-8 h-8 rounded-full border-2 transition-all duration-300 ${
                        isDone
                          ? 'bg-primary-500 border-primary-500 text-white'
                          : isActive
                          ? 'bg-white border-primary-500 text-primary-600 shadow-sm shadow-primary-200'
                          : 'bg-white border-gray-200 text-gray-300'
                      }`}
                    >
                      {isDone ? (
                        <CheckCircle2 className="h-4 w-4" />
                      ) : isActive ? (
                        <div className={`text-primary-600`}>{PHASE_ICONS[step.key]}</div>
                      ) : (
                        <span className="text-xs font-bold">{idx + 1}</span>
                      )}
                    </div>
                    <span className={`text-xs font-medium ${
                      isActive ? 'text-primary-700' : isDone ? 'text-primary-500' : 'text-gray-400'
                    }`}>
                      {step.label}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Live tender count */}
            <p className="text-xs text-primary-600 text-center">
              {isExtracting
                ? (stats.total > 0
                    ? `${stats.total} tender${stats.total !== 1 ? 's' : ''} found so far — updating live`
                    : 'Scanning for new tenders…')
                : `Done — ${stats.total} tender${stats.total !== 1 ? 's' : ''} in database`}
            </p>
          </div>
        )}
      </div>

      {/* Recent Activity */}
      <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-8">
        <h3 className="text-xl font-semibold text-gray-900 mb-6">Recent Activity</h3>
        <div className="space-y-4">
          {todaysTenders.length > 0 ? (
            todaysTenders.slice(0, 5).map((tender) => (
              <div key={tender.id} className="flex items-center justify-between py-3 border-b border-gray-100 last:border-b-0">
                <div className="flex items-center">
                  <div className={`w-3 h-3 rounded-full mr-4 ${
                    tender.passes_screening ? 'bg-green-500' : 'bg-amber-500'
                  }`}></div>
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      {tender.passes_screening ? 'Recommended match' : 'Low match'}{' '}
                      {typeof tender.screening_yes_count === 'number'
                        ? `(${tender.screening_yes_count}/5)`
                        : ''}
                    </p>
                    <p className="text-xs text-gray-500">{tender.title.substring(0, 60)}...</p>
                  </div>
                </div>
                <div className="flex items-center text-xs text-gray-500">
                  <Clock className="h-3 w-3 mr-1" />
                  {formatDate(tender.created_at)}
                </div>
              </div>
            ))
          ) : (
            <div className="text-center py-8">
              <div className="flex items-center justify-center text-gray-400 mb-2">
                <Clock className="h-8 w-8" />
              </div>
              <p className="text-gray-500">No tenders added yet today</p>
              <p className="text-xs text-gray-400 mt-1">
                After midnight, counts reset until you run a manual scan or the scheduler finds new rows
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};