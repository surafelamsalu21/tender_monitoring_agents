// services/api.ts - Complete API service with Test Crawler
import axios from 'axios';
import { Tender, Page, Keyword, SystemStatus } from '../types';

// API base: empty = same origin (CRA dev server proxies /api to backend — works from other PCs on LAN).
// Set REACT_APP_API_URL when the built UI is hosted separately from the API (e.g. http://192.168.1.10:8000).
const API_BASE_URL = (process.env.REACT_APP_API_URL || '').replace(/\/$/, '');

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // Increased timeout for crawler testing
});

const AUTH_TOKEN_STORAGE_KEY = 'tender_monitor_auth_token';

export interface AuthUser {
  id: number;
  email: string;
  full_name?: string;
  role: string;
  is_active: boolean;
  is_superuser?: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

// Add email settings types
export interface EmailNotificationSettings {
  opportunity_emails: string[];
  notification_preferences: {
    send_for_new_tenders: boolean;
    send_daily_summary: boolean;
    send_urgent_notifications: boolean;
  };
}

export interface EmailSettingsResponse {
  success: boolean;
  message: string;
  settings: EmailNotificationSettings;
}

export interface TestEmailRequest {
  email: string;
  category?: 'screening_opportunities';
}

export const getAuthToken = (): string | null => {
  return localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
};

export const setAuthToken = (token: string): void => {
  localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
};

export const clearAuthToken = (): void => {
  localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
};

api.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

type RetriableAxiosRequestConfig = Parameters<typeof axios.request>[0] & { _retry?: boolean };

function isAxiosErrorPayload(
  error: unknown
): error is {
  config: RetriableAxiosRequestConfig;
  response?: { status?: number };
  isAxiosError: true;
} {
  return (
    typeof error === 'object' &&
    error !== null &&
    'isAxiosError' in error &&
    (error as { isAxiosError?: boolean }).isAxiosError === true
  );
}

api.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!isAxiosErrorPayload(error) || !error.config) {
      return Promise.reject(error);
    }
    const cfg = error.config as RetriableAxiosRequestConfig;
    const url = String(cfg.url ?? '');
    if (
      error.response?.status === 401 &&
      !cfg._retry &&
      !url.includes('/auth/login') &&
      getAuthToken()
    ) {
      cfg._retry = true;
      cfg.headers = cfg.headers ?? {};
      cfg.headers.Authorization = `Bearer ${getAuthToken()}`;
      return api.request(cfg);
    }
    return Promise.reject(error);
  }
);

// NEW: Test Crawler types
export interface CrawlTestResult {
  status: 'success' | 'failed' | 'error';
  url: string;
  title?: string;
  markdown?: string;
  html?: string;
  links?: string[];
  media?: string[];
  metadata?: any;
  word_count?: number;
  char_count?: number;
  error?: string;
}

// Database backup types
export interface BackupFile {
  filename: string;
  size_bytes: number;
  size_human: string;
  created_at: string;
}

export interface BackupStatus {
  enabled: boolean;
  interval_hours: number;
  retention: number;
  directory: string;
  count: number;
  total_bytes: number;
  latest: BackupFile | null;
}

export interface BackupListResponse {
  success: boolean;
  status: BackupStatus;
  backups: BackupFile[];
}

export const apiRequest = async (
  endpoint: string,
  method: 'get' | 'post' | 'put' | 'patch' | 'delete' = 'get',
  data?: any,
  options: any = {}
) => {
  try {
    let response;
    if (method === 'get') {
      response = await api.get(endpoint, options);
    } else if (method === 'post') {
      response = await api.post(endpoint, data, options);
    } else if (method === 'put') {
      response = await api.put(endpoint, data, options);
    } else if (method === 'patch') {
      response = await api.patch(endpoint, data, options);
    } else if (method === 'delete') {
      response = await api.delete(endpoint, options);
    }
    return response?.data;
  } catch (error) {
    console.error(`API request failed for ${endpoint}:`, error);
    throw error;
  }
};

export const apiService = {
  // Auth
  login: async (email: string, password: string): Promise<LoginResponse> => {
    const data = await apiRequest('/api/v1/auth/login', 'post', { email, password });
    return data as LoginResponse;
  },

  getCurrentUser: async (): Promise<AuthUser> => {
    const data = await apiRequest('/api/v1/auth/me');
    return data as AuthUser;
  },

  updateProfile: async (payload: { full_name?: string | null }): Promise<AuthUser> => {
    const data = await apiRequest('/api/v1/auth/me', 'patch', payload);
    return data as AuthUser;
  },

  changePassword: async (
    old_password: string,
    new_password: string
  ): Promise<{ success: boolean; message: string }> => {
    const data = await apiRequest('/api/v1/auth/change-password', 'post', {
      old_password,
      new_password,
    });
    return data as { success: boolean; message: string };
  },

  createCompanyUser: async (payload: {
    email: string;
    password: string;
    full_name?: string;
    role: 'viewer' | 'analyst' | 'admin';
  }): Promise<AuthUser> => {
    const data = await apiRequest('/api/v1/admin/users', 'post', payload);
    return data as AuthUser;
  },

  adminSetUserPassword: async (
    email: string,
    new_password: string
  ): Promise<{ success: boolean; message: string }> => {
    const data = await apiRequest('/api/v1/admin/users/set-password', 'post', {
      email,
      new_password,
    });
    return data as { success: boolean; message: string };
  },

  // System
  checkHealth: async (): Promise<SystemStatus> => {
    const data = await apiRequest('/health');
    return data as SystemStatus;
  },
  
  getSystemStatus: async (): Promise<any> => {
    const data = await apiRequest('/api/v1/system/status');
    return data;
  },
    
  triggerExtraction: async (): Promise<{ message: string }> => {
    const data = await apiRequest('/trigger-extraction', 'post');
    return data as { message: string };
  },

  getExtractionStatus: async (): Promise<{ running: boolean; started_at: string | null }> => {
    const data = await apiRequest('/extraction-status');
    return data as { running: boolean; started_at: string | null };
  },

  getSchedulerStatus: async (): Promise<{
    active: boolean;
    interval_hours: number;
    in_progress: boolean;
    started_at: string | null;
    last_run_at: string | null;
    next_run_at: string | null;
  }> => {
    const data = await apiRequest('/scheduler-status');
    return data as {
      active: boolean;
      interval_hours: number;
      in_progress: boolean;
      started_at: string | null;
      last_run_at: string | null;
      next_run_at: string | null;
    };
  },

  // Tenders
  getTenders: async (): Promise<Tender[]> => {
    const data = await apiRequest('/api/v1/tenders/');
    return data as Tender[];
  },

  getTenderStatsSummary: async (localDayBounds?: {
    start: string;
    end: string;
  }): Promise<{
    total_tenders: number;
    passed_screening: number;
    failed_screening: number;
    recommended_screening: number;
    low_match_screening: number;
    recent_tenders_7_days: number;
    unnotified_tenders: number;
    tenders_added_today: number;
    tenders_added_today_recommended: number;
    tenders_added_today_low_match: number;
    last_updated: string;
  }> => {
    const params = new URLSearchParams();
    if (localDayBounds) {
      params.set('tenders_day_start', localDayBounds.start);
      params.set('tenders_day_end', localDayBounds.end);
    }
    const qs = params.toString();
    const data = await apiRequest(
      `/api/v1/tenders/stats/summary${qs ? `?${qs}` : ''}`
    );
    return data as {
      total_tenders: number;
      passed_screening: number;
      failed_screening: number;
      recommended_screening: number;
      low_match_screening: number;
      recent_tenders_7_days: number;
      unnotified_tenders: number;
      tenders_added_today: number;
      tenders_added_today_recommended: number;
      tenders_added_today_low_match: number;
      last_updated: string;
    };
  },

  // Get detailed tender information
  getTenderDetails: async (tenderId: number): Promise<Tender> => {
    const data = await apiRequest(`/api/v1/tenders/${tenderId}`);
    return data as Tender;
  },

  // Delete a tender (and its detailed info via cascade)
  deleteTender: async (tenderId: number): Promise<{ success: boolean; tender_id: number }> => {
    const data = await apiRequest(`/api/v1/tenders/${tenderId}`, 'delete');
    return data as { success: boolean; tender_id: number };
  },

  retryTenderDetail: async (
    tenderId: number,
    options?: { skipDateValidation?: boolean }
  ): Promise<{ success: boolean; tender_id: number; detailed_tender_id?: number | null }> => {
    const params = new URLSearchParams();
    if (options?.skipDateValidation) {
      params.set('skip_date_validation', 'true');
    }
    const qs = params.toString();
    const data = await apiRequest(
      `/api/v1/tenders/${tenderId}/retry-detail${qs ? `?${qs}` : ''}`,
      'post',
      undefined,
      { timeout: 180000 }
    );
    return data as { success: boolean; tender_id: number; detailed_tender_id?: number | null };
  },

  retryPendingTenderDetails: async (options?: {
    limit?: number;
    onlyPassedScreening?: boolean;
    skipDateValidation?: boolean;
  }): Promise<{
    success: boolean;
    attempted: number;
    completed: number;
    outcomes: Array<
      Record<string, unknown> & { tender_id: number; success?: boolean; message?: string }
    >;
  }> => {
    const params = new URLSearchParams();
    if (options?.limit != null) {
      params.set('limit', String(options.limit));
    }
    if (options?.onlyPassedScreening === false) {
      params.set('only_passed_screening', 'false');
    }
    if (options?.skipDateValidation) {
      params.set('skip_date_validation', 'true');
    }
    const qs = params.toString();
    const data = await apiRequest(
      `/api/v1/tenders/retry-pending-details${qs ? `?${qs}` : ''}`,
      'post',
      undefined,
      { timeout: 600000 }
    );
    return data as {
      success: boolean;
      attempted: number;
      completed: number;
      outcomes: Array<
        Record<string, unknown> & { tender_id: number; success?: boolean; message?: string }
      >;
    };
  },

  // Pages
  getPages: async (): Promise<Page[]> => {
    const data = await apiRequest('/api/v1/pages/');
    return data as Page[];
  },

  createPage: async (data: { url: string; name: string; crawl_strategy?: Page['crawl_strategy'] }): Promise<Page> => {
    const responseData = await apiRequest('/api/v1/pages/', 'post', data);
    return responseData as Page;
  },

  updatePage: async (id: number, data: Partial<Page>): Promise<Page> => {
    const response = await api.put(`/api/v1/pages/${id}`, data);
    return response.data as Page;
  },

  deletePage: async (id: number): Promise<void> => {
    await api.delete(`/api/v1/pages/${id}`);
  },

  // Keywords
  getKeywords: async (): Promise<Keyword[]> => {
    const data = await apiRequest('/api/v1/keywords/');
    return data as Keyword[];
  },

  createKeyword: async (data: { keyword: string; category: string }): Promise<Keyword> => {
    const responseData = await apiRequest('/api/v1/keywords/', 'post', data);
    return responseData as Keyword;
  },

  updateKeyword: async (id: number, data: Partial<Keyword>): Promise<Keyword> => {
    const response = await api.put(`/api/v1/keywords/${id}`, data);
    return response.data as Keyword;
  },

  deleteKeyword: async (id: number): Promise<void> => {
    await api.delete(`/api/v1/keywords/${id}`);
  },

  // Test Crawler - NEW METHOD
  testCrawler: async (url: string): Promise<CrawlTestResult> => {
    try {
      console.log(`Testing crawler for URL: ${url}`);
      const data = await apiRequest('/api/v1/system/test-crawler', 'post', { url });
      console.log('Crawler test result:', data);
      return data as CrawlTestResult;
    } catch (error) {
      console.error('Failed to test crawler:', error);
      return {
        status: 'error',
        url: url,
        error: 'Failed to test crawler. Please check your connection and try again.'
      };
    }
  },

  // Email Settings
  getEmailSettings: async (): Promise<EmailSettingsResponse> => {
    try {
      const data = await apiRequest('/api/v1/system/email-settings');
      return data as EmailSettingsResponse;
    } catch (error) {
      console.warn('Failed to load email settings from API, using defaults:', error);
      return {
        success: true,
        message: 'Using default settings',
        settings: {
          opportunity_emails: [],
          notification_preferences: {
            send_for_new_tenders: true,
            send_daily_summary: true,
            send_urgent_notifications: true,
          }
        }
      };
    }
  },

  saveEmailSettings: async (settings: EmailNotificationSettings): Promise<EmailSettingsResponse> => {
    try {
      const payload = {
        opportunity_emails: settings.opportunity_emails ?? [],
        notification_preferences: settings.notification_preferences,
      };
      const data = await apiRequest('/api/v1/system/email-settings', 'post', payload);
      return data as EmailSettingsResponse;
    } catch (error) {
      console.error('Failed to save email settings:', error);
      return {
        success: false,
        message: 'Failed to save email settings',
        settings: settings
      };
    }
  },

  sendTestEmail: async (request: TestEmailRequest): Promise<{ success: boolean; message: string; details?: string }> => {
    try {
      const data = await apiRequest('/api/v1/system/test-email', 'post', request);
      return data as { success: boolean; message: string; details?: string };
    } catch (error) {
      console.error('Failed to send test email:', error);
      return {
        success: false,
        message: 'Failed to send test email. Please check your email configuration.',
        details: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  },

  addEmailToCategory: async (category: string, email: string): Promise<{ success: boolean; message: string }> => {
    try {
      const data = await apiRequest(`/api/v1/system/email-settings/${category}/add`, 'post', { email });
      return data as { success: boolean; message: string };
    } catch (error) {
      console.error('Failed to add email:', error);
      return {
        success: false,
        message: 'Failed to add email'
      };
    }
  },

  removeEmailFromCategory: async (category: string, email: string): Promise<{ success: boolean; message: string }> => {
    try {
      const response = await api.delete(`/api/v1/system/email-settings/${category}/${encodeURIComponent(email)}`);
      return response.data as { success: boolean; message: string };
    } catch (error) {
      console.error('Failed to remove email:', error);
      return {
        success: false,
        message: 'Failed to remove email'
      };
    }
  },

  // Database Backups
  listBackups: async (): Promise<BackupListResponse> => {
    const data = await apiRequest('/api/v1/backup/');
    return data as BackupListResponse;
  },

  runBackupNow: async (): Promise<{ success: boolean; message: string; backup: BackupFile }> => {
    const data = await apiRequest('/api/v1/backup/run', 'post');
    return data as { success: boolean; message: string; backup: BackupFile };
  },

  deleteBackup: async (filename: string): Promise<{ success: boolean; message: string }> => {
    const data = await apiRequest(`/api/v1/backup/${encodeURIComponent(filename)}`, 'delete');
    return data as { success: boolean; message: string };
  },

  getBackupDownloadUrl: (filename: string): string =>
    `${API_BASE_URL}/api/v1/backup/download/${encodeURIComponent(filename)}`,
};