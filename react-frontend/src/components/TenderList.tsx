// components/TenderList.tsx - Complete Redesign with Working Modal
import React, { useState, useEffect } from 'react';
import { 
  Search, 
  Filter, 
  ExternalLink, 
  Calendar, 
  Tag, 
  Eye, 
  Clock, 
  Building, 
  AlertTriangle, 
  CheckCircle, 
  X, 
  Archive, 
  Zap,
  Trash2,
  User,
  Phone,
  Mail,
  MapPin,
  FileText,
  AlertCircle,
  DollarSign,
  RefreshCw
} from 'lucide-react';
import { Tender, CategoryType } from '../types';
import { apiService, AuthUser } from '../services/api';
import {
  formatAddedToDatabase,
  isTenderCreatedLocalToday,
} from '../utils/tenderDates';

interface TenderListProps {
  tenders: Tender[];
  onRefresh?: () => void | Promise<void>;
  currentUser?: AuthUser | null;
}

type ViewType = 'processed' | 'all' | 'active' | 'expired';
type SortType = 'newest' | 'oldest' | 'deadline' | 'urgent';

/** Human-readable countdown; negative days → Expired (not "-1"). */
function formatDaysUntilDeadlineValue(dv: {
  days_until_deadline?: number | null;
  deadline_status?: string;
  urgency_level?: string;
}): { text: string; className: string } | null {
  const d = dv.days_until_deadline;
  if (d === null || d === undefined) {
    if (dv.deadline_status === 'expired' || dv.urgency_level === 'expired') {
      return { text: 'Expired', className: 'text-red-700 font-semibold' };
    }
    return null;
  }
  const expired =
    d < 0 || dv.deadline_status === 'expired' || dv.urgency_level === 'expired';
  if (expired) {
    return { text: 'Expired', className: 'text-red-700 font-semibold' };
  }
  if (d === 0) {
    return { text: 'Due today', className: 'text-amber-700 font-medium' };
  }
  return {
    text: `${d} ${d === 1 ? 'day' : 'days'}`,
    className: 'text-gray-800',
  };
}

export const TenderList: React.FC<TenderListProps> = ({ tenders, onRefresh, currentUser }) => {
  const canDelete = !!currentUser && (
    currentUser.role === 'super_admin' ||
    currentUser.role === 'superadmin' ||
    currentUser.is_superuser === true
  );

  // State management
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<CategoryType>('all');
  const [selectedView, setSelectedView] = useState<ViewType>('active');
  const [sortBy, setSortBy] = useState<SortType>('newest');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedTender, setSelectedTender] = useState<Tender | null>(null);
  const [detailedTender, setDetailedTender] = useState<Tender | null>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

  // Delete-confirmation modal state
  const [tenderPendingDelete, setTenderPendingDelete] = useState<Tender | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const [retryingId, setRetryingId] = useState<number | null>(null);
  const [bulkRetrying, setBulkRetrying] = useState(false);
  const [retryMessage, setRetryMessage] = useState<string | null>(null);

  const requestDelete = (tender: Tender) => {
    setTenderPendingDelete(tender);
    setDeleteError(null);
  };

  const cancelDelete = () => {
    if (isDeleting) return;
    setTenderPendingDelete(null);
    setDeleteError(null);
  };

  const confirmDelete = async () => {
    if (!tenderPendingDelete) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await apiService.deleteTender(tenderPendingDelete.id);
      setTenderPendingDelete(null);
      if (onRefresh) await onRefresh();
    } catch (err) {
      console.error('Failed to delete tender:', err);
      setDeleteError(err instanceof Error ? err.message : 'Failed to delete tender');
    } finally {
      setIsDeleting(false);
    }
  };

  const retryDetailExtraction = async (tender: Tender, skipDateValidation: boolean) => {
    if (!currentUser) return;
    setRetryMessage(null);
    setRetryingId(tender.id);
    try {
      await apiService.retryTenderDetail(tender.id, { skipDateValidation });
      setRetryMessage(`Details saved for tender #${tender.id}.`);
      if (onRefresh) await onRefresh();
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } }; message?: string };
      const msg =
        ax?.response?.data?.detail ||
        (err instanceof Error ? err.message : 'Retry failed');
      setRetryMessage(msg);
      console.error('Retry detail extraction failed:', err);
    } finally {
      setRetryingId(null);
    }
  };

  const retryPendingBulk = async () => {
    if (!currentUser) return;
    setRetryMessage(null);
    setBulkRetrying(true);
    try {
      const res = await apiService.retryPendingTenderDetails({
        limit: 20,
        onlyPassedScreening: true,
        skipDateValidation: false,
      });
      setRetryMessage(
        `Bulk retry: ${res.completed}/${res.attempted} tender(s) completed detail extraction.`
      );
      if (onRefresh) await onRefresh();
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } }; message?: string };
      const msg =
        ax?.response?.data?.detail ||
        (err instanceof Error ? err.message : 'Bulk retry failed');
      setRetryMessage(msg);
      console.error('Bulk retry failed:', err);
    } finally {
      setBulkRetrying(false);
    }
  };

  // Close modal on escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isModalOpen) {
        closeModal();
      }
    };
    
    if (isModalOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden'; // Prevent background scroll
    }
    
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isModalOpen]);

  const getUrgencyScore = (tender: Tender): number => {
    const dateValidation = tender.detailed_info?.date_validation;
    if (!dateValidation || !dateValidation.urgency_level) return 0;

    switch (dateValidation.urgency_level) {
      case 'urgent':
        return 5;
      case 'high':
        return 4;
      case 'medium':
        return 3;
      case 'low':
        return 2;
      case 'expired':
        return 1;
      default:
        return 0;
    }
  };

  // Filter and sort tenders
  const getFilteredTenders = () => {
    let filtered = [...tenders];

    // Apply view filter
    switch (selectedView) {
      case 'processed':
        filtered = filtered.filter(t => t.is_processed);
        break;
      case 'all':
        // Show all tenders
        break;
      case 'active':
        filtered = filtered.filter(t => {
          if (!t.detailed_info?.date_validation) return true;
          return ['active', 'urgent'].includes(t.detailed_info.date_validation.deadline_status || '');
        });
        break;
      case 'expired':
        filtered = filtered.filter(t => {
          if (!t.detailed_info?.date_validation) return false;
          return t.detailed_info.date_validation.deadline_status === 'expired';
        });
        break;
    }

    // Apply search filter
    if (searchTerm) {
      filtered = filtered.filter(tender => 
        tender.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (tender.description && tender.description.toLowerCase().includes(searchTerm.toLowerCase()))
      );
    }

    // Apply category filter
    if (selectedCategory === 'passed') {
      filtered = filtered.filter(tender => tender.passes_screening === true);
    } else if (selectedCategory === 'failed') {
      filtered = filtered.filter(tender => tender.passes_screening === false);
    }

    // Apply sorting (local "today" rows first, then chosen sort)
    filtered.sort((a, b) => {
      const aToday = isTenderCreatedLocalToday(a.created_at) ? 1 : 0;
      const bToday = isTenderCreatedLocalToday(b.created_at) ? 1 : 0;
      if (bToday !== aToday) return bToday - aToday;
      switch (sortBy) {
        case 'newest':
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        case 'oldest':
          return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
        case 'deadline':
          const deadlineA = a.detailed_info?.deadline || a.tender_date;
          const deadlineB = b.detailed_info?.deadline || b.tender_date;
          if (!deadlineA && !deadlineB) return 0;
          if (!deadlineA) return 1;
          if (!deadlineB) return -1;
          return new Date(deadlineA).getTime() - new Date(deadlineB).getTime();
        case 'urgent':
          return getUrgencyScore(b) - getUrgencyScore(a);
        default:
          return 0;
      }
    });

    return filtered;
  };

  const filteredTenders = getFilteredTenders();

  const formatDate = (dateString: string | null | undefined) => {
    if (!dateString) return 'N/A';
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
    } catch (e) {
      return 'Invalid Date';
    }
  };

  const screeningYesFraction = (tender: Tender) =>
    typeof tender.screening_yes_count === 'number'
      ? `${tender.screening_yes_count}/5`
      : '—';

  const screeningBadgeClasses = (tender: Tender) => {
    if (tender.passes_screening === true)
      return 'bg-emerald-100 text-emerald-900 border-emerald-200';
    return 'bg-amber-50 text-amber-900 border-amber-300';
  };

  const screeningBadgeLabel = (tender: Tender) =>
    tender.passes_screening === true
      ? `Recommended · ${screeningYesFraction(tender)}`
      : `Low match · ${screeningYesFraction(tender)}`;

  const screeningCardAccent = (tender: Tender) =>
    tender.passes_screening === true
      ? 'border-l-[6px] border-emerald-500'
      : 'border-l-[6px] border-amber-400 bg-amber-50/40';

  const getUrgencyDisplay = (tender: Tender) => {
    const dateValidation = tender.detailed_info?.date_validation;
    if (!dateValidation) return null;

    const { urgency_level, days_until_deadline } = dateValidation;

    const urgencyConfig = {
      urgent: { color: 'text-red-700', bg: 'bg-red-100', border: 'border-red-200', icon: AlertTriangle, text: 'Urgent' },
      high: { color: 'text-orange-700', bg: 'bg-orange-100', border: 'border-orange-200', icon: Clock, text: 'High Priority' },
      medium: { color: 'text-yellow-700', bg: 'bg-yellow-100', border: 'border-yellow-200', icon: Clock, text: 'Medium' },
      low: { color: 'text-green-700', bg: 'bg-green-100', border: 'border-green-200', icon: CheckCircle, text: 'Low' },
      expired: { color: 'text-red-800', bg: 'bg-red-100', border: 'border-red-300', icon: Trash2, text: 'Expired' }
    };

    const config = urgencyConfig[urgency_level as keyof typeof urgencyConfig];
    if (!config) return null;

    const Icon = config.icon;

    return (
      <div className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${config.bg} ${config.color} ${config.border}`}>
        <Icon className="h-3 w-3 mr-1" />
        {config.text}
        {days_until_deadline !== null && days_until_deadline !== undefined && days_until_deadline >= 0 && (
          <span className="ml-1">({days_until_deadline}d)</span>
        )}
      </div>
    );
  };

  const getViewStats = () => {
    const processed = tenders.filter(t => t.is_processed).length;
    const all = tenders.length;
    const active = tenders.filter(t => {
      if (!t.detailed_info?.date_validation) return true;
      return ['active', 'urgent'].includes(t.detailed_info.date_validation.deadline_status || '');
    }).length;
    const expired = tenders.filter(t => {
      if (!t.detailed_info?.date_validation) return false;
      return t.detailed_info.date_validation.deadline_status === 'expired';
    }).length;

    return { processed, all, active, expired };
  };

  const stats = getViewStats();

  // Modal functions
  const openModal = async (tender: Tender) => {
    setSelectedTender(tender);
    setIsModalOpen(true);
    setLoadingDetails(true);
    
    try {
      const detailed = await apiService.getTenderDetails(tender.id);
      setDetailedTender(detailed);
    } catch (error) {
      console.error('Failed to load tender details:', error);
      setDetailedTender(tender);
    } finally {
      setLoadingDetails(false);
    }
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedTender(null);
    setDetailedTender(null);
    setLoadingDetails(false);
  };

  // Parse contact info helper
  const parseContactInfo = (contactInfo: any) => {
    if (typeof contactInfo === 'string') {
      try {
        return JSON.parse(contactInfo);
      } catch {
        return { organization: contactInfo };
      }
    }
    return contactInfo || {};
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto p-6">
        {/* Header */}
        <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">Tender Management</h1>
            <p className="text-gray-600">Manage and view all tender opportunities processed by our AI agents</p>
          </div>
          {currentUser && (
            <button
              type="button"
              onClick={() => void retryPendingBulk()}
              disabled={bulkRetrying}
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border border-amber-300 bg-amber-50 text-amber-900 text-sm font-medium hover:bg-amber-100 disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
              title="Re-run Agent 2 for up to 20 recommended tenders still pending detail extraction"
            >
              <RefreshCw className={`h-4 w-4 ${bulkRetrying ? 'animate-spin' : ''}`} />
              {bulkRetrying ? 'Retrying…' : 'Retry pending details (batch)'}
            </button>
          )}
        </div>
        {retryMessage && (
          <div
            className="mb-4 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800"
            role="status"
          >
            {retryMessage}
          </div>
        )}

        {/* View Tabs */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 mb-6">
          <div className="p-6 border-b border-gray-200">
            <div className="flex flex-wrap gap-2">
              {[
                { id: 'active', label: 'Active', count: stats.active, icon: Zap },
                { id: 'processed', label: 'Processed', count: stats.processed, icon: CheckCircle },
                { id: 'all', label: 'All Tenders', count: stats.all, icon: Archive },
                { id: 'expired', label: 'Expired', count: stats.expired, icon: Trash2 },
              ].map((view) => {
                const Icon = view.icon;
                const isSel = selectedView === view.id;

                const selectedClass =
                  view.id === 'active'
                    ? 'bg-emerald-600 text-white shadow-md ring-2 ring-emerald-300 border-transparent'
                    : view.id === 'processed'
                      ? 'bg-primary-600 text-white shadow-md border-transparent'
                      : view.id === 'all'
                        ? 'bg-slate-700 text-white shadow-md border-transparent'
                        : 'bg-red-600 text-white shadow-md ring-2 ring-red-400 border-transparent';

                const idleClass =
                  view.id === 'active'
                    ? 'bg-emerald-50 text-emerald-900 border-emerald-200 hover:bg-emerald-100'
                    : view.id === 'processed'
                      ? 'bg-primary-50 text-primary-900 border-primary-200 hover:bg-primary-100'
                      : view.id === 'all'
                        ? 'bg-gray-100 text-gray-800 border-gray-200 hover:bg-gray-200'
                        : 'bg-red-50 text-red-900 border-red-200 hover:bg-red-100';

                return (
                  <button
                    key={view.id}
                    onClick={() => setSelectedView(view.id as ViewType)}
                    className={`flex items-center px-4 py-2 rounded-lg font-medium text-sm transition-all duration-200 border ${isSel ? selectedClass : idleClass}`}
                  >
                    <Icon className="h-4 w-4 mr-2 shrink-0" />
                    {view.label} ({view.count})
                  </button>
                );
              })}
            </div>
          </div>

          {/* Search and Filters */}
          <div className="p-6">
            <div className="flex flex-col lg:flex-row gap-4">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 h-5 w-5" />
                <input
                  type="text"
                  placeholder="Search tenders by title or description..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-colors"
                />
              </div>
              
              <div className="flex gap-3">
                <div className="relative">
                  <Filter className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 h-4 w-4" />
                  <select
                    value={selectedCategory}
                    onChange={(e) => setSelectedCategory(e.target.value as CategoryType)}
                    className="pl-10 pr-8 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent appearance-none bg-white min-w-[140px]"
                  >
                    <option value="all">All screening tiers</option>
                    <option value="passed">Recommended (≥3/5)</option>
                    <option value="failed">Low match (1–2/5)</option>
                  </select>
                </div>
                
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as SortType)}
                  className="px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent appearance-none bg-white min-w-[120px]"
                >
                  <option value="newest">Newest First</option>
                  <option value="oldest">Oldest First</option>
                  <option value="deadline">By Deadline</option>
                  <option value="urgent">By Urgency</option>
                </select>
              </div>
            </div>

            {/* View Description */}
            <div
              className={`mt-4 p-3 rounded-lg border ${
                selectedView === 'expired'
                  ? 'bg-red-50 border-red-200'
                  : selectedView === 'active'
                    ? 'bg-emerald-50 border-emerald-200'
                    : selectedView === 'processed'
                      ? 'bg-primary-50 border-primary-200'
                      : 'bg-slate-50 border-slate-200'
              }`}
            >
              <p
                className={`text-sm ${
                  selectedView === 'expired'
                    ? 'text-red-900'
                    : selectedView === 'active'
                      ? 'text-emerald-900'
                      : selectedView === 'processed'
                        ? 'text-primary-900'
                        : 'text-slate-800'
                }`}
              >
                {selectedView === 'processed' && "Showing tenders that have been processed by Agent 2 with detailed information."}
                {selectedView === 'all' && "Showing all tenders extracted by Agent 1, including unprocessed ones."}
                {selectedView === 'active' && "Showing only tenders with active deadlines (not expired)."}
                {selectedView === 'expired' && "Showing tenders with expired deadlines or old publication dates."}
                {selectedCategory === 'passed' && (
                  <span className="block mt-2 font-medium">Category filter: recommended matches only (≥3 of 5 Step 1 criteria).</span>
                )}
                {selectedCategory === 'failed' && (
                  <span className="block mt-2 font-medium">Category filter: low matches only (1–2 of 5 criteria — still shortlisted for visibility).</span>
                )}
              </p>
            </div>
          </div>
        </div>

        {/* Tender Cards */}
        <div className="space-y-4">
          {filteredTenders.length === 0 ? (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
              <Archive className="h-16 w-16 text-gray-400 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-gray-900 mb-2">No tenders found</h3>
              <p className="text-gray-500 mb-4">No tenders match your current filters and search criteria.</p>
              <button 
                onClick={() => {
                  setSearchTerm('');
                  setSelectedCategory('all');
                  setSelectedView('all');
                }}
                className="text-primary-600 hover:text-primary-700 font-medium"
              >
                Clear all filters
              </button>
            </div>
          ) : (
            filteredTenders.map((tender) => {
              const isNewToday = isTenderCreatedLocalToday(tender.created_at);
              return (
              <div
                key={tender.id}
                className={`rounded-xl shadow-sm border hover:shadow-lg transition-all duration-200 group ${
                  isNewToday
                    ? 'ring-2 ring-emerald-400/90 border-emerald-200 bg-emerald-50/50'
                    : 'border-gray-200 bg-white'
                } ${screeningCardAccent(tender)}`}
              >
                <div className="p-6">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      {/* Header */}
                      <div className="flex items-start gap-3 mb-3">
                        <h3 className="text-lg font-semibold text-gray-900 group-hover:text-primary-600 transition-colors flex-1 min-w-0">
                          {tender.title}
                        </h3>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <span className={`px-3 py-1 rounded-full text-xs font-medium border ${screeningBadgeClasses(tender)}`}>
                            <Tag className="h-3 w-3 inline mr-1" />
                            {screeningBadgeLabel(tender)}
                          </span>
                        </div>
                      </div>
                      
                      {/* Status badges */}
                      <div className="flex items-center gap-2 mb-3 flex-wrap">
                        {tender.is_processed ? (
                          <span className="inline-flex items-center text-xs text-emerald-700 bg-emerald-100 px-2 py-1 rounded-full border border-emerald-200">
                            <CheckCircle className="h-3 w-3 mr-1" />
                            Processed by AI
                          </span>
                        ) : (
                          <span className="inline-flex items-center text-xs text-orange-700 bg-orange-100 px-2 py-1 rounded-full border border-orange-200">
                            <Clock className="h-3 w-3 mr-1" />
                            Pending Processing
                          </span>
                        )}
                        
                        {getUrgencyDisplay(tender)}
                        
                        {tender.is_notified && (
                          <span className="inline-flex items-center text-xs text-primary-700 bg-primary-100 px-2 py-1 rounded-full border border-primary-200">
                            <CheckCircle className="h-3 w-3 mr-1" />
                            Notified
                          </span>
                        )}
                        {isNewToday && (
                          <span className="inline-flex items-center text-xs font-semibold text-emerald-900 bg-emerald-200/90 px-2 py-1 rounded-full border border-emerald-400">
                            Added today
                          </span>
                        )}
                      </div>
                      
                      {/* Description */}
                      {tender.description && (
                        <p className="text-gray-600 text-sm mb-4 line-clamp-2">
                          {tender.description}
                        </p>
                      )}
                      
                      {/* Footer */}
                      <div className="flex items-center justify-between">
                        <div className="flex items-center text-sm text-gray-500 space-x-4 flex-wrap gap-y-1">
                          <div
                            className="flex items-center"
                            title="When this row was saved to the database"
                          >
                            <Clock className="h-4 w-4 mr-1 text-gray-400" />
                            <span className="text-gray-600">
                              Added: {formatAddedToDatabase(tender.created_at)}
                            </span>
                          </div>
                          <div className="flex items-center">
                            <Calendar className="h-4 w-4 mr-1" />
                            Notice: {formatDate(tender.tender_date)}
                          </div>
                          {tender.detailed_info?.deadline && (
                            <div className="flex items-center">
                              <Clock className="h-4 w-4 mr-1" />
                              Deadline: {formatDate(tender.detailed_info.deadline)}
                            </div>
                          )}
                          {tender.page_name && (
                            <div className="flex items-center">
                              <Building className="h-4 w-4 mr-1" />
                              {tender.page_name}
                            </div>
                          )}
                        </div>
                        
                        <div className="flex items-center space-x-2 flex-wrap gap-y-2">
                          {tender.is_processed && (
                            <button
                              onClick={() => openModal(tender)}
                              className="inline-flex items-center px-3 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
                            >
                              <Eye className="h-4 w-4 mr-1" />
                              View Details
                            </button>
                          )}
                          {!tender.is_processed && tender.url && currentUser && (
                            <>
                              <button
                                type="button"
                                onClick={() => void retryDetailExtraction(tender, false)}
                                disabled={retryingId === tender.id || bulkRetrying}
                                className="inline-flex items-center px-3 py-2 border border-amber-300 bg-amber-50 text-amber-900 rounded-lg hover:bg-amber-100 transition-colors text-sm font-medium disabled:opacity-50"
                                title="Re-run Agent 2 detail extraction for this tender"
                              >
                                <RefreshCw
                                  className={`h-4 w-4 mr-1 ${retryingId === tender.id ? 'animate-spin' : ''}`}
                                />
                                Retry details
                              </button>
                              <button
                                type="button"
                                onClick={() => void retryDetailExtraction(tender, true)}
                                disabled={retryingId === tender.id || bulkRetrying}
                                className="inline-flex items-center px-2 py-2 text-xs font-medium text-amber-800 hover:text-amber-950 underline-offset-2 hover:underline disabled:opacity-50"
                                title="Same as Retry details but skips Agent 2 deadline / date filtering (for stubborn listings)"
                              >
                                No date filter
                              </button>
                            </>
                          )}
                          <a
                            href={tender.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center p-2 text-primary-600 hover:text-primary-700 hover:bg-primary-50 rounded-lg transition-colors"
                            title="Open original tender"
                          >
                            <ExternalLink className="h-4 w-4" />
                          </a>
                          {canDelete && (
                            <button
                              onClick={() => requestDelete(tender)}
                              className="inline-flex items-center p-2 text-red-600 hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors"
                              title="Delete tender (super admin only)"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            );
            })
          )}
        </div>

        {/* Results Summary */}
        <div className="mt-8 text-center text-sm text-gray-500">
          Showing {filteredTenders.length} of {tenders.length} tenders
          {selectedView === 'processed' && ` • ${stats.processed} processed by AI`}
          {selectedView === 'active' && ` • ${stats.active} active tenders`}
          {selectedView === 'expired' && ` • ${stats.expired} expired tenders`}
        </div>
      </div>

      {/* Modal */}
      {isModalOpen && (
        <div 
          className="fixed inset-0 z-50 overflow-y-auto"
          aria-labelledby="modal-title" 
          role="dialog" 
          aria-modal="true"
        >
          <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
            {/* Background overlay */}
            <div 
              className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" 
              aria-hidden="true"
              onClick={closeModal}
            ></div>

            {/* This element is to trick the browser into centering the modal contents. */}
            <span className="hidden sm:inline-block sm:align-middle sm:h-screen" aria-hidden="true">&#8203;</span>

            {/* Modal panel */}
            <div className="relative inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-4xl sm:w-full">
              {/* Header */}
              <div className="bg-white px-6 py-4 border-b border-gray-200">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-xl font-semibold text-gray-900" id="modal-title">
                      {detailedTender?.detailed_info?.detailed_title || selectedTender?.title || 'Tender Details'}
                    </h3>
                    {selectedTender && (
                      <div className="flex items-center gap-3 mt-2 flex-wrap">
                        <span className={`px-3 py-1 rounded-full text-sm font-medium border ${screeningBadgeClasses(selectedTender)}`}>
                          <Tag className="h-4 w-4 inline mr-1" />
                          {screeningBadgeLabel(selectedTender)}
                        </span>
                        {detailedTender?.detailed_info?.deadline && (
                          <span className="flex items-center text-sm text-gray-600">
                            <Clock className="h-4 w-4 mr-1" />
                            Deadline: {formatDate(detailedTender.detailed_info.deadline)}
                          </span>
                        )}
                        {getUrgencyDisplay(selectedTender)}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={closeModal}
                    className="ml-4 p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    <X className="h-6 w-6 text-gray-400" />
                  </button>
                </div>
              </div>

              {/* Content */}
              <div className="bg-white px-6 py-6 max-h-[70vh] overflow-y-auto">
                {loadingDetails ? (
                  <div className="flex items-center justify-center py-12">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
                    <span className="ml-3 text-gray-600">Loading detailed information...</span>
                  </div>
                ) : detailedTender ? (
                  <div className="space-y-6">
                    {/* Key Details Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="bg-primary-50 p-4 rounded-lg border border-primary-200">
                        <div className="flex items-center mb-2">
                          <Building className="h-5 w-5 text-primary-600 mr-2" />
                          <span className="font-semibold text-primary-900">Organization</span>
                        </div>
                        <p className="text-primary-800 text-sm">
                          {(() => {
                            const contactInfo = parseContactInfo(detailedTender.detailed_info?.contact_info);
                            return contactInfo.organization || 'Not specified';
                          })()}
                        </p>
                      </div>
                      
                      <div className="bg-green-50 p-4 rounded-lg border border-green-200">
                        <div className="flex items-center mb-2">
                          <DollarSign className="h-5 w-5 text-green-600 mr-2" />
                          <span className="font-semibold text-green-900">Value</span>
                        </div>
                        <p className="text-green-800 text-sm">
                          {detailedTender.detailed_info?.tender_value || 'Not specified'}
                        </p>
                      </div>
                      
                      <div className="bg-primary-50 p-4 rounded-lg border border-primary-200">
                        <div className="flex items-center mb-2">
                          <Clock className="h-5 w-5 text-primary-600 mr-2" />
                          <span className="font-semibold text-primary-900">Duration</span>
                        </div>
                        <p className="text-primary-800 text-sm">
                          {detailedTender.detailed_info?.duration || 'Not specified'}
                        </p>
                      </div>
                    </div>

                    {/* Description */}
                    {detailedTender.detailed_info?.detailed_description && (
                      <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                        <h4 className="text-lg font-semibold text-gray-900 mb-3 flex items-center">
                          <FileText className="h-5 w-5 mr-2" />
                          Description
                        </h4>
                        <p className="text-gray-700 leading-relaxed text-sm whitespace-pre-wrap">
                          {detailedTender.detailed_info.detailed_description}
                        </p>
                      </div>
                    )}

                    {/* Requirements */}
                    {detailedTender.detailed_info?.requirements && (
                      <div className="bg-orange-50 p-4 rounded-lg border border-orange-200">
                        <h4 className="text-lg font-semibold text-orange-900 mb-3 flex items-center">
                          <CheckCircle className="h-5 w-5 mr-2" />
                          Requirements
                        </h4>
                        <div className="text-orange-800 leading-relaxed text-sm">
                          {detailedTender.detailed_info.requirements.includes('\n') ? (
                            <ul className="list-disc list-inside space-y-1">
                              {detailedTender.detailed_info.requirements.split('\n').filter(req => req.trim()).map((req, index) => (
                                <li key={index}>{req.trim()}</li>
                              ))}
                            </ul>
                          ) : (
                            <p>{detailedTender.detailed_info.requirements}</p>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Contact Information */}
                    <div className="bg-primary-50 p-4 rounded-lg border border-primary-200">
                      <h4 className="text-lg font-semibold text-primary-900 mb-3 flex items-center">
                        <User className="h-5 w-5 mr-2" />
                        Contact Information
                      </h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {(() => {
                          const contactInfo = parseContactInfo(detailedTender.detailed_info?.contact_info);
                          const contactPerson = contactInfo.contact_person || 'Unknown';
                          const contactEmail = contactInfo.email || 'Unknown';

                          return (
                            <>
                              <div className="flex items-center">
                                <User className="h-4 w-4 text-primary-600 mr-2 flex-shrink-0" />
                                <span className="text-primary-800 text-sm">{contactPerson}</span>
                              </div>
                              <div className="flex items-center col-span-1 md:col-span-2">
                                <Mail className="h-4 w-4 text-primary-600 mr-2 flex-shrink-0" />
                                {contactInfo.email ? (
                                  <a href={`mailto:${contactInfo.email}`} className="text-primary-600 hover:underline text-sm">
                                    {contactInfo.email}
                                  </a>
                                ) : (
                                  <span className="text-primary-800 text-sm">{contactEmail}</span>
                                )}
                              </div>
                              {contactInfo.phone && (
                                <div className="flex items-center">
                                  <Phone className="h-4 w-4 text-primary-600 mr-2 flex-shrink-0" />
                                  <span className="text-primary-800 text-sm">{contactInfo.phone}</span>
                                </div>
                              )}
                              {contactInfo.address && (
                                <div className="flex items-start col-span-1 md:col-span-2">
                                  <MapPin className="h-4 w-4 text-primary-600 mr-2 mt-0.5 flex-shrink-0" />
                                  <span className="text-primary-800 text-sm">{contactInfo.address}</span>
                                </div>
                              )}
                            </>
                          );
                        })()}
                      </div>
                    </div>

                    {/* Additional Details */}
                    {detailedTender.detailed_info?.additional_details && (
                      <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                        <h4 className="text-lg font-semibold text-gray-900 mb-3 flex items-center">
                          <AlertCircle className="h-5 w-5 mr-2" />
                          Additional Details
                        </h4>
                        <p className="text-gray-700 leading-relaxed text-sm whitespace-pre-wrap">
                          {detailedTender.detailed_info.additional_details}
                        </p>
                      </div>
                    )}

                    {/* Documents Required */}
                    {detailedTender.detailed_info?.documents_required && (
                      <div className="bg-yellow-50 p-4 rounded-lg border border-yellow-200">
                        <h4 className="text-lg font-semibold text-yellow-900 mb-3 flex items-center">
                          <FileText className="h-5 w-5 mr-2" />
                          Required Documents
                        </h4>
                        <p className="text-yellow-800 leading-relaxed text-sm">
                          {detailedTender.detailed_info.documents_required}
                        </p>
                      </div>
                    )}

                    {/* Evaluation Criteria */}
                    {detailedTender.detailed_info?.evaluation_criteria && (
                      <div className="bg-primary-50 p-4 rounded-lg border border-primary-200">
                        <h4 className="text-lg font-semibold text-primary-900 mb-3 flex items-center">
                          <CheckCircle className="h-5 w-5 mr-2" />
                          Evaluation Criteria
                        </h4>
                        <p className="text-primary-800 leading-relaxed text-sm">
                          {detailedTender.detailed_info.evaluation_criteria}
                        </p>
                      </div>
                    )}

                    {/* Processing Status */}
                    {detailedTender.detailed_info?.date_validation && (
                      <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                        <h4 className="text-lg font-semibold text-gray-900 mb-3 flex items-center">
                          <Clock className="h-5 w-5 mr-2" />
                          Processing Information
                        </h4>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          <div>
                            <span className="text-sm font-medium text-gray-600">Status:</span>
                            <span className="ml-2 text-sm text-gray-800 capitalize">
                              {detailedTender.detailed_info.date_validation.deadline_status || 'Unknown'}
                            </span>
                          </div>
                          <div>
                            <span className="text-sm font-medium text-gray-600">Urgency:</span>
                            <span className="ml-2 text-sm text-gray-800 capitalize">
                              {detailedTender.detailed_info.date_validation.urgency_level || 'Unknown'}
                            </span>
                          </div>
                          {(() => {
                            const dv = detailedTender.detailed_info.date_validation;
                            const display = formatDaysUntilDeadlineValue(dv);
                            if (!display) return null;
                            return (
                              <div className="col-span-2">
                                <span className="text-sm font-medium text-gray-600">Days until deadline:</span>
                                <span className={`ml-2 text-sm ${display.className}`}>{display.text}</span>
                              </div>
                            );
                          })()}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <AlertCircle className="h-16 w-16 text-gray-400 mx-auto mb-4" />
                    <h3 className="text-lg font-semibold text-gray-900 mb-2">No detailed information available</h3>
                    <p className="text-gray-500 mb-4">This tender may not have been processed by Agent 2 yet.</p>
                    <p className="text-sm text-gray-400">Try refreshing the page or check back later.</p>
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex justify-between items-center">
                <div className="text-sm text-gray-500">
                  {selectedTender && (
                    <span>
                      Added on {formatDate(selectedTender.created_at)}
                      {selectedTender.page_name && ` from ${selectedTender.page_name}`}
                    </span>
                  )}
                </div>
                <div className="flex space-x-3">
                  <button
                    onClick={closeModal}
                    className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    Close
                  </button>
                  {selectedTender && (
                    <a
                      href={selectedTender.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
                    >
                      <ExternalLink className="h-4 w-4 mr-2" />
                      View Original
                    </a>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirmation modal */}
      {tenderPendingDelete && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60] p-4"
          onClick={cancelDelete}
        >
          <div
            className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 animate-fade-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-4">
              <div className="shrink-0 w-12 h-12 rounded-full bg-red-50 flex items-center justify-center">
                <AlertTriangle className="h-6 w-6 text-red-600" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-lg font-semibold text-gray-900">Delete this tender?</h3>
                <p className="text-sm text-gray-600 mt-1">
                  This permanently removes the tender and its detailed information from the database. This action cannot be undone.
                </p>
                <div className="mt-3 p-3 rounded-lg bg-gray-50 border border-gray-200">
                  <p className="text-sm font-medium text-gray-800 line-clamp-2">
                    {tenderPendingDelete.title}
                  </p>
                  {tenderPendingDelete.page_name && (
                    <p className="text-xs text-gray-500 mt-1 flex items-center">
                      <Building className="h-3 w-3 mr-1" />
                      {tenderPendingDelete.page_name}
                    </p>
                  )}
                </div>
                {deleteError && (
                  <div className="mt-3 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
                    {deleteError}
                  </div>
                )}
              </div>
            </div>
            <div className="flex items-center justify-end gap-3 mt-6">
              <button
                onClick={cancelDelete}
                disabled={isDeleting}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={isDeleting}
                className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isDeleting ? (
                  <>
                    <svg className="animate-spin h-4 w-4 mr-2" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                      <path fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" className="opacity-75" />
                    </svg>
                    Deleting...
                  </>
                ) : (
                  <>
                    <Trash2 className="h-4 w-4 mr-2" />
                    Delete
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};