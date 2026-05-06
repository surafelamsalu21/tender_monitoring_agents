// components/Settings.tsx - Fixed email management functionality
import React, { useState, useEffect } from 'react';
import {
  Clock,
  Mail,
  Database,
  Server,
  CheckCircle,
  AlertCircle,
  Loader,
  Plus,
  Trash2,
  Users,
  Send,
  RefreshCw,
  Download,
  HardDrive
} from 'lucide-react';
import { apiService, BackupFile, BackupStatus, getAuthToken } from '../services/api';

interface EmailNotificationSettings {
  opportunity_emails: string[];
  notification_preferences: {
    send_for_new_tenders: boolean;
    send_daily_summary: boolean;
    send_urgent_notifications: boolean;
  };
}

export const Settings: React.FC = () => {
  const [systemStatus, setSystemStatus] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [emailSettings, setEmailSettings] = useState<EmailNotificationSettings>({
    opportunity_emails: [],
    notification_preferences: {
      send_for_new_tenders: true,
      send_daily_summary: true,
      send_urgent_notifications: true,
    }
  });
  
  // Email form states
  const [newRecipientEmail, setNewRecipientEmail] = useState('');
  const [emailErrors, setEmailErrors] = useState<{ [key: string]: string }>({});
  const [isSaving, setIsSaving] = useState(false);
  const [testingEmail, setTestingEmail] = useState<string | null>(null);
  const [processingEmails, setProcessingEmails] = useState<Set<string>>(new Set());
  const [refreshing, setRefreshing] = useState(false);

  // Backup state
  const [backups, setBackups] = useState<BackupFile[]>([]);
  const [backupStatus, setBackupStatus] = useState<BackupStatus | null>(null);
  const [backupLoading, setBackupLoading] = useState(false);
  const [backupRunning, setBackupRunning] = useState(false);
  const [backupError, setBackupError] = useState<string | null>(null);
  const [deletingBackup, setDeletingBackup] = useState<string | null>(null);

  // Scheduler (extraction) status
  const [schedulerStatus, setSchedulerStatus] = useState<{
    active: boolean;
    interval_hours: number;
    in_progress: boolean;
    started_at: string | null;
    last_run_at: string | null;
    next_run_at: string | null;
  } | null>(null);
  const [schedulerLoading, setSchedulerLoading] = useState(false);

  useEffect(() => {
    const fetchSystemStatus = async () => {
      try {
        setLoading(true);
        const status = await apiService.getSystemStatus();
        setSystemStatus(status);
        setError(null);

        // Load existing email settings from database
        await loadEmailSettings();
        await loadBackups();
        await loadSchedulerStatus();
      } catch (err) {
        setError('Failed to load system status');
        console.error('Error fetching system status:', err);
        // Still try to load email settings even if system status fails
        await loadEmailSettings();
        await loadBackups();
        await loadSchedulerStatus();
      } finally {
        setLoading(false);
      }
    };

    fetchSystemStatus();

    // Refresh scheduler status periodically while the user is on this page.
    const tick = setInterval(() => {
      loadSchedulerStatus().catch(() => undefined);
    }, 30_000);
    return () => clearInterval(tick);
  }, []);

  const loadSchedulerStatus = async () => {
    setSchedulerLoading(true);
    try {
      const status = await apiService.getSchedulerStatus();
      setSchedulerStatus(status);
    } catch (err) {
      console.error('Error loading scheduler status:', err);
    } finally {
      setSchedulerLoading(false);
    }
  };

  const loadBackups = async () => {
    setBackupLoading(true);
    setBackupError(null);
    try {
      const response = await apiService.listBackups();
      setBackups(response.backups || []);
      setBackupStatus(response.status || null);
    } catch (err) {
      console.error('Error loading backups:', err);
      setBackupError('Failed to load backups');
    } finally {
      setBackupLoading(false);
    }
  };

  const runBackupNow = async () => {
    setBackupRunning(true);
    setBackupError(null);
    try {
      const response = await apiService.runBackupNow();
      if (!response.success) {
        setBackupError(response.message || 'Backup failed');
      }
      await loadBackups();
    } catch (err: any) {
      console.error('Error running backup:', err);
      const detail =
        err?.response?.data?.detail || err?.message || 'Backup failed';
      setBackupError(String(detail));
    } finally {
      setBackupRunning(false);
    }
  };

  const downloadBackup = async (filename: string) => {
    try {
      const url = apiService.getBackupDownloadUrl(filename);
      const token = getAuthToken();
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        setBackupError(`Download failed: ${res.status}`);
        return;
      }
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (err) {
      console.error('Error downloading backup:', err);
      setBackupError('Failed to download backup');
    }
  };

  const removeBackup = async (filename: string) => {
    if (!window.confirm(`Delete backup ${filename}? This cannot be undone.`)) {
      return;
    }
    setDeletingBackup(filename);
    try {
      const response = await apiService.deleteBackup(filename);
      if (!response.success) {
        setBackupError(response.message || 'Delete failed');
      }
      await loadBackups();
    } catch (err: any) {
      console.error('Error deleting backup:', err);
      setBackupError(err?.response?.data?.detail || 'Failed to delete backup');
    } finally {
      setDeletingBackup(null);
    }
  };

  const loadEmailSettings = async () => {
    try {
      console.log('Loading email settings from API...');
      
      const response = await apiService.getEmailSettings();
      console.log('Email settings API response:', response);
      
      if (response.success && response.settings) {
        console.log('Setting email settings from API:', response.settings);
        setEmailSettings({
          opportunity_emails: response.settings.opportunity_emails ?? [],
          notification_preferences: response.settings.notification_preferences || {
            send_for_new_tenders: true,
            send_daily_summary: true,
            send_urgent_notifications: true,
          }
        });
      } else {
        console.warn('API returned unsuccessful response or missing settings:', response);
        // Use default settings if API returns unsuccessful
        setEmailSettings({
          opportunity_emails: [],
          notification_preferences: {
            send_for_new_tenders: true,
            send_daily_summary: true,
            send_urgent_notifications: true,
          }
        });
      }
    } catch (error) {
      console.error('Error loading email settings:', error);
      // Fallback to default settings on any error
      setEmailSettings({
        opportunity_emails: [],
        notification_preferences: {
          send_for_new_tenders: true,
          send_daily_summary: true,
          send_urgent_notifications: true,
        }
      });
    }
  };

  const refreshEmailSettings = async () => {
    setRefreshing(true);
    try {
      await loadEmailSettings();
    } catch (error) {
      console.error('Error refreshing email settings:', error);
    } finally {
      setRefreshing(false);
    }
  };

  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const addRecipientEmail = async () => {
    if (!newRecipientEmail.trim()) {
      setEmailErrors({ ...emailErrors, recipients: 'Email is required' });
      return;
    }

    if (!validateEmail(newRecipientEmail)) {
      setEmailErrors({ ...emailErrors, recipients: 'Please enter a valid email address' });
      return;
    }

    if (emailSettings.opportunity_emails.includes(newRecipientEmail)) {
      setEmailErrors({ ...emailErrors, recipients: 'Email already exists' });
      return;
    }

    try {
      const updatedSettings = {
        ...emailSettings,
        opportunity_emails: [...emailSettings.opportunity_emails, newRecipientEmail],
      };

      const saveResponse = await apiService.saveEmailSettings(updatedSettings);

      if (saveResponse.success) {
        setEmailSettings(updatedSettings);
        setNewRecipientEmail('');
        setEmailErrors({ ...emailErrors, recipients: '' });
        await loadEmailSettings();
      } else {
        setEmailErrors({
          ...emailErrors,
          recipients: `Failed to add email: ${saveResponse.message}`,
        });
      }
    } catch (error) {
      console.error('Error adding recipient email:', error);
      setEmailErrors({ ...emailErrors, recipients: 'Failed to add email. Please try again.' });
    }
  };

  const removeRecipientEmail = async (emailToRemove: string) => {
    if (processingEmails.has(emailToRemove)) {
      return;
    }

    try {
      setProcessingEmails((prev) => new Set(prev).add(emailToRemove));

      const updatedSettings = {
        ...emailSettings,
        opportunity_emails: emailSettings.opportunity_emails.filter((e) => e !== emailToRemove),
      };

      const saveResponse = await apiService.saveEmailSettings(updatedSettings);

      if (saveResponse.success) {
        setEmailSettings(updatedSettings);
        await loadEmailSettings();
      } else {
        alert(`Failed to remove email: ${saveResponse.message}`);
      }
    } catch (error) {
      console.error('Error removing recipient email:', error);
      alert('Failed to remove email. Please try again.');
    } finally {
      setProcessingEmails((prev) => {
        const next = new Set(prev);
        next.delete(emailToRemove);
        return next;
      });
    }
  };

  const updateNotificationPreference = (key: keyof typeof emailSettings.notification_preferences, value: boolean) => {
    setEmailSettings({
      ...emailSettings,
      notification_preferences: {
        ...emailSettings.notification_preferences,
        [key]: value
      }
    });
  };

  const saveEmailSettings = async () => {
    setIsSaving(true);
    try {
      const response = await apiService.saveEmailSettings(emailSettings);
      
      if (response.success) {
        alert('Email settings saved successfully!');
        // Refresh settings to ensure consistency
        await loadEmailSettings();
      } else {
        alert(`Failed to save email settings: ${response.message}`);
      }
    } catch (error) {
      console.error('Failed to save email settings:', error);
      alert('Failed to save email settings. Please check your connection and try again.');
    } finally {
      setIsSaving(false);
    }
  };

  const sendTestEmail = async (email: string, category: 'screening_opportunities') => {
    setTestingEmail(email);
    try {
      const response = await apiService.sendTestEmail({ email, category });
      
      if (response.success) {
        alert(`Test email sent successfully to ${email}!`);
      } else {
        alert(`Failed to send test email: ${response.message}`);
      }
    } catch (error) {
      console.error('Failed to send test email:', error);
      alert('Failed to send test email. Please check your email configuration and try again.');
    } finally {
      setTestingEmail(null);
    }
  };

  const renderEmailList = (emails: string[], category: 'screening_opportunities', removeFunction: (email: string) => void) => (
    <div className="space-y-2">
      {emails.length === 0 ? (
        <div className="text-center py-6 text-gray-500 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
          <Mail className="h-8 w-8 mx-auto mb-2 text-gray-400" />
          <p>No email addresses configured</p>
          <p className="text-sm">Add an email address to receive notifications</p>
        </div>
      ) : (
        emails.map((email, index) => (
          <div key={`${email}-${index}`} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border">
            <div className="flex items-center">
              <Mail className="h-4 w-4 text-gray-500 mr-2" />
              <span className="text-sm font-medium text-gray-900">{email}</span>
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => sendTestEmail(email, category)}
                disabled={testingEmail === email}
                className="flex items-center px-2 py-1 text-xs bg-primary-100 text-primary-700 rounded hover:bg-primary-200 transition-colors disabled:opacity-50"
                title="Send test email"
              >
                {testingEmail === email ? (
                  <Loader className="h-3 w-3 animate-spin" />
                ) : (
                  <Send className="h-3 w-3" />
                )}
              </button>
              <button
                onClick={() => removeFunction(email)}
                disabled={processingEmails.has(email)}
                className="p-1 text-red-600 hover:bg-red-50 rounded transition-colors disabled:opacity-50"
                title="Remove email"
              >
                {processingEmails.has(email) ? (
                  <Loader className="h-3 w-3 animate-spin" />
                ) : (
                  <Trash2 className="h-3 w-3" />
                )}
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Settings</h2>

      {/* Email Notifications - Enhanced Section */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-6 flex items-center justify-between">
          <div className="flex items-center">
            <Mail className="h-5 w-5 mr-2" />
            Email Notifications Management
          </div>
          <button
            onClick={refreshEmailSettings}
            disabled={refreshing}
            className="flex items-center px-3 py-1 text-sm bg-primary-100 text-primary-700 rounded-lg hover:bg-primary-200 transition-colors disabled:opacity-50"
          >
            {refreshing ? (
              <Loader className="h-4 w-4 mr-1 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-1" />
            )}
            Refresh Settings
          </button>
        </h3>
        
        <div className="space-y-8">
          {/* Debug Info */}
          <div className="bg-gray-50 p-4 rounded-lg border-2 border-dashed border-gray-300">
            <h4 className="text-sm font-medium text-gray-700 mb-2">Current Status:</h4>
            <div className="text-xs text-gray-600 space-y-1">
              <div>Screening notification emails: {emailSettings.opportunity_emails.length} configured</div>
              <div>Loading: {loading ? 'Yes' : 'No'}</div>
              <div>Last Refresh: {new Date().toLocaleTimeString()}</div>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-4">
              <h4 className="text-md font-medium text-gray-800 flex items-center">
                <Users className="h-4 w-4 mr-2 text-primary-600" />
                Opportunity screening alerts ({emailSettings.opportunity_emails.length})
              </h4>
            </div>
            <p className="text-sm text-gray-600 mb-4">
              Recipients get notifications for opportunities that pass the Precise screening checklist (Steps 1–3).
            </p>

            <div className="mb-4 p-4 bg-primary-50 rounded-lg border border-primary-200">
              <div className="flex items-center space-x-3">
                <div className="flex-1">
                  <input
                    type="email"
                    value={newRecipientEmail}
                    onChange={(e) => {
                      setNewRecipientEmail(e.target.value);
                      if (emailErrors.recipients) setEmailErrors({ ...emailErrors, recipients: '' });
                    }}
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addRecipientEmail();
                      }
                    }}
                    placeholder="Email address for screening alerts"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  />
                  {emailErrors.recipients && (
                    <p className="text-red-600 text-sm mt-1">{emailErrors.recipients}</p>
                  )}
                </div>
                <button
                  onClick={addRecipientEmail}
                  disabled={!newRecipientEmail.trim()}
                  className="flex items-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add
                </button>
              </div>
            </div>

            {renderEmailList(emailSettings.opportunity_emails, 'screening_opportunities', removeRecipientEmail)}
          </div>

          {/* Notification Preferences */}
          <div className="border-t pt-6">
            <h4 className="text-md font-medium text-gray-800 mb-4">Notification Preferences</h4>
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <label className="text-sm font-medium text-gray-700">New opportunity alerts</label>
                  <p className="text-xs text-gray-500">Notify when new screened opportunities are captured</p>
                </div>
                <input
                  type="checkbox"
                  checked={emailSettings.notification_preferences.send_for_new_tenders}
                  onChange={(e) => updateNotificationPreference('send_for_new_tenders', e.target.checked)}
                  className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                />
              </div>
              
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <label className="text-sm font-medium text-gray-700">Daily summary</label>
                  <p className="text-xs text-gray-500">Daily digest of screening activity</p>
                </div>
                <input
                  type="checkbox"
                  checked={emailSettings.notification_preferences.send_daily_summary}
                  onChange={(e) => updateNotificationPreference('send_daily_summary', e.target.checked)}
                  className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                />
              </div>
              
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <label className="text-sm font-medium text-gray-700">Urgent notifications</label>
                  <p className="text-xs text-gray-500">Highlight time-sensitive deadlines</p>
                </div>
                <input
                  type="checkbox"
                  checked={emailSettings.notification_preferences.send_urgent_notifications}
                  onChange={(e) => updateNotificationPreference('send_urgent_notifications', e.target.checked)}
                  className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                />
              </div>
            </div>
          </div>

          {/* Save Button */}
          <div className="flex justify-between items-center pt-4 border-t">
            <div className="text-sm text-gray-600">
              Total recipients: {emailSettings.opportunity_emails.length}
            </div>
            <button
              onClick={saveEmailSettings}
              disabled={isSaving}
              className="flex items-center px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
            >
              {isSaving ? (
                <>
                  <Loader className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <CheckCircle className="h-4 w-4 mr-2" />
                  Save Email Settings
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Rest of the Settings components remain unchanged */}
      {/* Recent Activity */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Recent Activity</h3>
        <div className="overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader className="h-6 w-6 text-primary-500 animate-spin" />
            </div>
          ) : error ? (
            <div className="text-center py-4 text-red-500">Failed to load activity data</div>
          ) : systemStatus?.recent_activity && systemStatus.recent_activity.length > 0 ? (
            <table className="min-w-full divide-y divide-gray-200">
              <thead>
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Page ID</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Tenders</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {systemStatus.recent_activity.map((activity: any, index: number) => (
                  <tr key={index}>
                    <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-900">Page {activity.page_id}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-500">
                      {new Date(activity.started_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${activity.status === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                        {activity.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-900">
                      {activity.tenders_found}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="text-center py-4 text-gray-500">No recent activity found</div>
          )}
        </div>
      </div>

      {/* System Configuration */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
          <Server className="h-5 w-5 mr-2" />
          System Configuration
        </h3>
        
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader className="h-8 w-8 text-primary-500 animate-spin" />
            <span className="ml-2 text-gray-600">Loading system status...</span>
          </div>
        ) : error ? (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center">
            <AlertCircle className="h-5 w-5 text-red-500 mr-2" />
            <span className="text-red-700">{error}</span>
          </div>
        ) : systemStatus ? (
          <div className="space-y-4">
            <div className="flex items-center mb-2">
              <CheckCircle className="h-5 w-5 text-green-500 mr-2" />
              <span className="text-green-700 font-medium">System is {systemStatus.system?.status || 'running'}</span>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Backend URL
                </label>
                <input
                  type="url"
                  value="http://localhost:8000"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50"
                  disabled
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  API Version
                </label>
                <input
                  type="text"
                  value={systemStatus.system?.version || 'v1'}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50"
                  disabled
                />
              </div>
            </div>
            
            <div className="mt-4">
              <h4 className="text-md font-medium text-gray-800 mb-2">Database Statistics</h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-primary-50 p-3 rounded-lg">
                  <div className="text-sm text-gray-600">Total Pages</div>
                  <div className="text-xl font-semibold">{systemStatus.database?.total_pages || 0}</div>
                </div>
                <div className="bg-green-50 p-3 rounded-lg">
                  <div className="text-sm text-gray-600">Active Pages</div>
                  <div className="text-xl font-semibold">{systemStatus.database?.active_pages || 0}</div>
                </div>
                <div className="bg-primary-50 p-3 rounded-lg">
                  <div className="text-sm text-gray-600">Total Tenders</div>
                  <div className="text-xl font-semibold">{systemStatus.database?.total_tenders || 0}</div>
                </div>
                <div className="bg-yellow-50 p-3 rounded-lg">
                  <div className="text-sm text-gray-600">Active Keywords</div>
                  <div className="text-xl font-semibold">{systemStatus.database?.active_keywords || 0}</div>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Backend URL
              </label>
              <input
                type="url"
                value="http://localhost:8000"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50"
                disabled
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                API Version
              </label>
              <input
                type="text"
                value="v1"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50"
                disabled
              />
            </div>
          </div>
        )}
      </div>
      
      {/* Extraction Schedule (fixed) */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center justify-between">
          <span className="flex items-center">
            <Clock className="h-5 w-5 mr-2" />
            Extraction Schedule
          </span>
          <button
            onClick={loadSchedulerStatus}
            disabled={schedulerLoading}
            className="flex items-center px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50"
            title="Refresh status"
          >
            {schedulerLoading ? (
              <Loader className="h-4 w-4 mr-1 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-1" />
            )}
            Refresh
          </button>
        </h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Extraction Frequency
            </label>
            <input
              type="text"
              value={`Every ${schedulerStatus?.interval_hours ?? 12} hours (fixed)`}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-700"
              disabled
            />
            <p className="text-xs text-gray-500 mt-1">
              The scheduler runs automatically at this cadence. The cadence is fixed system-wide.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="bg-green-50 p-3 rounded-lg">
              <div className="text-xs text-gray-600">Status</div>
              <div className="text-sm font-semibold flex items-center">
                {schedulerStatus?.active ? (
                  <>
                    <span className="w-2 h-2 bg-green-500 rounded-full mr-2 animate-pulse"></span>
                    {schedulerStatus.in_progress ? 'Running now' : 'Active'}
                  </>
                ) : (
                  <>
                    <span className="w-2 h-2 bg-gray-400 rounded-full mr-2"></span>
                    Stopped
                  </>
                )}
              </div>
            </div>
            <div className="bg-primary-50 p-3 rounded-lg">
              <div className="text-xs text-gray-600">Last extraction</div>
              <div className="text-sm font-semibold">
                {schedulerStatus?.last_run_at
                  ? new Date(schedulerStatus.last_run_at).toLocaleString()
                  : 'Not yet (since startup)'}
              </div>
            </div>
            <div className="bg-yellow-50 p-3 rounded-lg">
              <div className="text-xs text-gray-600">Next extraction</div>
              <div className="text-sm font-semibold">
                {schedulerStatus?.next_run_at
                  ? new Date(schedulerStatus.next_run_at).toLocaleString()
                  : 'Pending'}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Database Backups */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center justify-between">
          <span className="flex items-center">
            <Database className="h-5 w-5 mr-2" />
            Database Backups
          </span>
          <button
            onClick={loadBackups}
            disabled={backupLoading}
            className="flex items-center px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50"
            title="Refresh list"
          >
            {backupLoading ? (
              <Loader className="h-4 w-4 mr-1 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-1" />
            )}
            Refresh
          </button>
        </h3>

        {backupError && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start">
            <AlertCircle className="h-4 w-4 text-red-500 mr-2 mt-0.5 flex-shrink-0" />
            <span className="text-sm text-red-700">{backupError}</span>
          </div>
        )}

        {backupStatus && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
            <div className="bg-primary-50 p-3 rounded-lg">
              <div className="text-xs text-gray-600">Backups stored</div>
              <div className="text-xl font-semibold">{backupStatus.count}</div>
            </div>
            <div className="bg-green-50 p-3 rounded-lg">
              <div className="text-xs text-gray-600">Schedule</div>
              <div className="text-sm font-semibold">
                {backupStatus.enabled
                  ? `Every ${backupStatus.interval_hours}h`
                  : 'Disabled'}
              </div>
            </div>
            <div className="bg-yellow-50 p-3 rounded-lg">
              <div className="text-xs text-gray-600">Retention</div>
              <div className="text-sm font-semibold">
                Keep last {backupStatus.retention}
              </div>
            </div>
            <div className="bg-gray-50 p-3 rounded-lg">
              <div className="text-xs text-gray-600">Latest</div>
              <div className="text-sm font-semibold truncate">
                {backupStatus.latest
                  ? new Date(backupStatus.latest.created_at).toLocaleString()
                  : 'None yet'}
              </div>
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 mb-4">
          <button
            onClick={runBackupNow}
            disabled={backupRunning}
            className="flex items-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
          >
            {backupRunning ? (
              <>
                <Loader className="h-4 w-4 mr-2 animate-spin" />
                Backing up...
              </>
            ) : (
              <>
                <HardDrive className="h-4 w-4 mr-2" />
                Run Backup Now
              </>
            )}
          </button>
          {backupStatus?.directory && (
            <span className="text-xs text-gray-500 truncate" title={backupStatus.directory}>
              Location: {backupStatus.directory}
            </span>
          )}
        </div>

        {backupLoading && backups.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-gray-500">
            <Loader className="h-5 w-5 mr-2 animate-spin" />
            Loading backups...
          </div>
        ) : backups.length === 0 ? (
          <div className="text-center py-8 text-gray-500 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
            <Database className="h-8 w-8 mx-auto mb-2 text-gray-400" />
            <p>No backups yet</p>
            <p className="text-sm">
              The first scheduled backup runs ~5 minutes after the server starts.
            </p>
          </div>
        ) : (
          <div className="overflow-hidden border border-gray-200 rounded-lg">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Filename
                  </th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Created
                  </th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Size
                  </th>
                  <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {backups.map((b) => (
                  <tr key={b.filename}>
                    <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-900 font-mono">
                      {b.filename}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-600">
                      {new Date(b.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-600">
                      {b.size_human}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => downloadBackup(b.filename)}
                          className="flex items-center px-2 py-1 text-xs bg-primary-100 text-primary-700 rounded hover:bg-primary-200 transition-colors"
                          title="Download backup"
                        >
                          <Download className="h-3 w-3 mr-1" />
                          Download
                        </button>
                        <button
                          onClick={() => removeBackup(b.filename)}
                          disabled={deletingBackup === b.filename}
                          className="flex items-center px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200 transition-colors disabled:opacity-50"
                          title="Delete backup"
                        >
                          {deletingBackup === b.filename ? (
                            <Loader className="h-3 w-3 animate-spin" />
                          ) : (
                            <>
                              <Trash2 className="h-3 w-3 mr-1" />
                              Delete
                            </>
                          )}
                        </button>
                      </div>
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