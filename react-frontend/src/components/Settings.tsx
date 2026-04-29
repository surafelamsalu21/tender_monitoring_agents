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
  RefreshCw
} from 'lucide-react';
import { apiService } from '../services/api';

interface EmailNotificationSettings {
  esg_emails: string[];
  credit_rating_emails: string[];
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
    esg_emails: [],
    credit_rating_emails: [],
    notification_preferences: {
      send_for_new_tenders: true,
      send_daily_summary: true,
      send_urgent_notifications: true,
    }
  });
  
  // Email form states
  const [newEsgEmail, setNewEsgEmail] = useState('');
  const [newCreditEmail, setNewCreditEmail] = useState('');
  const [emailErrors, setEmailErrors] = useState<{ [key: string]: string }>({});
  const [isSaving, setIsSaving] = useState(false);
  const [testingEmail, setTestingEmail] = useState<string | null>(null);
  const [processingEmails, setProcessingEmails] = useState<Set<string>>(new Set());
  const [refreshing, setRefreshing] = useState(false);
  
  useEffect(() => {
    const fetchSystemStatus = async () => {
      try {
        setLoading(true);
        const status = await apiService.getSystemStatus();
        setSystemStatus(status);
        setError(null);
        
        // Load existing email settings from database
        await loadEmailSettings();
      } catch (err) {
        setError('Failed to load system status');
        console.error('Error fetching system status:', err);
        // Still try to load email settings even if system status fails
        await loadEmailSettings();
      } finally {
        setLoading(false);
      }
    };
    
    fetchSystemStatus();
  }, []);

  const loadEmailSettings = async () => {
    try {
      console.log('Loading email settings from API...');
      
      const response = await apiService.getEmailSettings();
      console.log('Email settings API response:', response);
      
      if (response.success && response.settings) {
        console.log('Setting email settings from API:', response.settings);
        setEmailSettings({
          esg_emails: response.settings.esg_emails || [],
          credit_rating_emails: response.settings.credit_rating_emails || [],
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
          esg_emails: [],
          credit_rating_emails: [],
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
        esg_emails: [],
        credit_rating_emails: [],
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

  const addEsgEmail = async () => {
    if (!newEsgEmail.trim()) {
      setEmailErrors({ ...emailErrors, esg: 'Email is required' });
      return;
    }
    
    if (!validateEmail(newEsgEmail)) {
      setEmailErrors({ ...emailErrors, esg: 'Please enter a valid email address' });
      return;
    }
    
    if (emailSettings.esg_emails.includes(newEsgEmail)) {
      setEmailErrors({ ...emailErrors, esg: 'Email already exists' });
      return;
    }
    
    try {
      console.log('Adding ESG email:', newEsgEmail);
      
      // First, optimistically update the local state
      const updatedSettings = {
        ...emailSettings,
        esg_emails: [...emailSettings.esg_emails, newEsgEmail]
      };
      
      // Save the entire settings object to the backend
      const saveResponse = await apiService.saveEmailSettings(updatedSettings);
      console.log('Save email settings response:', saveResponse);
      
      if (saveResponse.success) {
        // Update local state only after successful API call
        setEmailSettings(updatedSettings);
        setNewEsgEmail('');
        setEmailErrors({ ...emailErrors, esg: '' });
        console.log('ESG email added successfully');
        
        // Refresh settings from backend to ensure consistency
        await loadEmailSettings();
      } else {
        setEmailErrors({ ...emailErrors, esg: `Failed to add email: ${saveResponse.message}` });
      }
    } catch (error) {
      console.error('Error adding ESG email:', error);
      setEmailErrors({ ...emailErrors, esg: 'Failed to add email. Please try again.' });
    }
  };

  const addCreditEmail = async () => {
    if (!newCreditEmail.trim()) {
      setEmailErrors({ ...emailErrors, credit: 'Email is required' });
      return;
    }
    
    if (!validateEmail(newCreditEmail)) {
      setEmailErrors({ ...emailErrors, credit: 'Please enter a valid email address' });
      return;
    }
    
    if (emailSettings.credit_rating_emails.includes(newCreditEmail)) {
      setEmailErrors({ ...emailErrors, credit: 'Email already exists' });
      return;
    }
    
    try {
      console.log('Adding Credit email:', newCreditEmail);
      
      // First, optimistically update the local state
      const updatedSettings = {
        ...emailSettings,
        credit_rating_emails: [...emailSettings.credit_rating_emails, newCreditEmail]
      };
      
      // Save the entire settings object to the backend
      const saveResponse = await apiService.saveEmailSettings(updatedSettings);
      console.log('Save credit email settings response:', saveResponse);
      
      if (saveResponse.success) {
        // Update local state only after successful API call
        setEmailSettings(updatedSettings);
        setNewCreditEmail('');
        setEmailErrors({ ...emailErrors, credit: '' });
        console.log('Credit email added successfully');
        
        // Refresh settings from backend to ensure consistency
        await loadEmailSettings();
      } else {
        setEmailErrors({ ...emailErrors, credit: `Failed to add email: ${saveResponse.message}` });
      }
    } catch (error) {
      console.error('Error adding Credit email:', error);
      setEmailErrors({ ...emailErrors, credit: 'Failed to add email. Please try again.' });
    }
  };

  const removeEsgEmail = async (emailToRemove: string) => {
    if (processingEmails.has(emailToRemove)) {
      console.log('Email removal already in progress:', emailToRemove);
      return;
    }
    
    try {
      console.log('Removing ESG email:', emailToRemove);
      setProcessingEmails(prev => new Set(prev).add(emailToRemove));
      
      // Update local state optimistically
      const updatedSettings = {
        ...emailSettings,
        esg_emails: emailSettings.esg_emails.filter(email => email !== emailToRemove)
      };
      
      // Save the entire settings object to the backend
      const saveResponse = await apiService.saveEmailSettings(updatedSettings);
      console.log('Remove ESG email settings response:', saveResponse);
      
      if (saveResponse.success) {
        // Update local state only after successful API call
        setEmailSettings(updatedSettings);
        console.log('ESG email removed successfully');
        
        // Refresh settings from backend to ensure consistency
        await loadEmailSettings();
      } else {
        console.error('Failed to remove email via API:', saveResponse.message);
        alert(`Failed to remove email: ${saveResponse.message}`);
      }
    } catch (error) {
      console.error('Error removing ESG email:', error);
      alert('Failed to remove email. Please try again.');
    } finally {
      setProcessingEmails(prev => {
        const newSet = new Set(prev);
        newSet.delete(emailToRemove);
        return newSet;
      });
    }
  };

  const removeCreditEmail = async (emailToRemove: string) => {
    if (processingEmails.has(emailToRemove)) {
      console.log('Email removal already in progress:', emailToRemove);
      return;
    }
    
    try {
      console.log('Removing Credit email:', emailToRemove);
      setProcessingEmails(prev => new Set(prev).add(emailToRemove));
      
      // Update local state optimistically
      const updatedSettings = {
        ...emailSettings,
        credit_rating_emails: emailSettings.credit_rating_emails.filter(email => email !== emailToRemove)
      };
      
      // Save the entire settings object to the backend
      const saveResponse = await apiService.saveEmailSettings(updatedSettings);
      console.log('Remove credit email settings response:', saveResponse);
      
      if (saveResponse.success) {
        // Update local state only after successful API call
        setEmailSettings(updatedSettings);
        console.log('Credit email removed successfully');
        
        // Refresh settings from backend to ensure consistency
        await loadEmailSettings();
      } else {
        console.error('Failed to remove email via API:', saveResponse.message);
        alert(`Failed to remove email: ${saveResponse.message}`);
      }
    } catch (error) {
      console.error('Error removing Credit email:', error);
      alert('Failed to remove email. Please try again.');
    } finally {
      setProcessingEmails(prev => {
        const newSet = new Set(prev);
        newSet.delete(emailToRemove);
        return newSet;
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

  const sendTestEmail = async (email: string, category: 'esg' | 'credit_rating') => {
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

  const renderEmailList = (emails: string[], category: 'esg' | 'credit_rating', removeFunction: (email: string) => void) => (
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
                className="flex items-center px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition-colors disabled:opacity-50"
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
            className="flex items-center px-3 py-1 text-sm bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 transition-colors disabled:opacity-50"
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
              <div>ESG Emails: {emailSettings.esg_emails.length} configured</div>
              <div>Credit Rating Emails: {emailSettings.credit_rating_emails.length} configured</div>
              <div>Loading: {loading ? 'Yes' : 'No'}</div>
              <div>Last Refresh: {new Date().toLocaleTimeString()}</div>
            </div>
          </div>

          {/* ESG Team Emails */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h4 className="text-md font-medium text-gray-800 flex items-center">
                <Users className="h-4 w-4 mr-2 text-green-600" />
                ESG Team Notifications ({emailSettings.esg_emails.length})
              </h4>
            </div>
            
            {/* Add ESG Email Form */}
            <div className="mb-4 p-4 bg-green-50 rounded-lg border border-green-200">
              <div className="flex items-center space-x-3">
                <div className="flex-1">
                  <input
                    type="email"
                    value={newEsgEmail}
                    onChange={(e) => {
                      setNewEsgEmail(e.target.value);
                      if (emailErrors.esg) setEmailErrors({ ...emailErrors, esg: '' });
                    }}
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addEsgEmail();
                      }
                    }}
                    placeholder="Enter ESG team email address"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent"
                  />
                  {emailErrors.esg && (
                    <p className="text-red-600 text-sm mt-1">{emailErrors.esg}</p>
                  )}
                </div>
                <button
                  onClick={addEsgEmail}
                  disabled={!newEsgEmail.trim()}
                  className="flex items-center px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add
                </button>
              </div>
            </div>
            
            {/* ESG Email List */}
            {renderEmailList(emailSettings.esg_emails, 'esg', removeEsgEmail)}
          </div>

          {/* Credit Rating Team Emails */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h4 className="text-md font-medium text-gray-800 flex items-center">
                <Users className="h-4 w-4 mr-2 text-purple-600" />
                Credit Rating Team Notifications ({emailSettings.credit_rating_emails.length})
              </h4>
            </div>
            
            {/* Add Credit Email Form */}
            <div className="mb-4 p-4 bg-purple-50 rounded-lg border border-purple-200">
              <div className="flex items-center space-x-3">
                <div className="flex-1">
                  <input
                    type="email"
                    value={newCreditEmail}
                    onChange={(e) => {
                      setNewCreditEmail(e.target.value);
                      if (emailErrors.credit) setEmailErrors({ ...emailErrors, credit: '' });
                    }}
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addCreditEmail();
                      }
                    }}
                    placeholder="Enter Credit Rating team email address"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  />
                  {emailErrors.credit && (
                    <p className="text-red-600 text-sm mt-1">{emailErrors.credit}</p>
                  )}
                </div>
                <button
                  onClick={addCreditEmail}
                  disabled={!newCreditEmail.trim()}
                  className="flex items-center px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add
                </button>
              </div>
            </div>
            
            {/* Credit Email List */}
            {renderEmailList(emailSettings.credit_rating_emails, 'credit_rating', removeCreditEmail)}
          </div>

          {/* Notification Preferences */}
          <div className="border-t pt-6">
            <h4 className="text-md font-medium text-gray-800 mb-4">Notification Preferences</h4>
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <label className="text-sm font-medium text-gray-700">New Tender Notifications</label>
                  <p className="text-xs text-gray-500">Send immediate notifications when new tenders are found</p>
                </div>
                <input
                  type="checkbox"
                  checked={emailSettings.notification_preferences.send_for_new_tenders}
                  onChange={(e) => updateNotificationPreference('send_for_new_tenders', e.target.checked)}
                  className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                />
              </div>
              
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <label className="text-sm font-medium text-gray-700">Daily Summary</label>
                  <p className="text-xs text-gray-500">Send daily summary of all tender activities</p>
                </div>
                <input
                  type="checkbox"
                  checked={emailSettings.notification_preferences.send_daily_summary}
                  onChange={(e) => updateNotificationPreference('send_daily_summary', e.target.checked)}
                  className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                />
              </div>
              
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <label className="text-sm font-medium text-gray-700">Urgent Notifications</label>
                  <p className="text-xs text-gray-500">Send urgent notifications for time-sensitive tenders</p>
                </div>
                <input
                  type="checkbox"
                  checked={emailSettings.notification_preferences.send_urgent_notifications}
                  onChange={(e) => updateNotificationPreference('send_urgent_notifications', e.target.checked)}
                  className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                />
              </div>
            </div>
          </div>

          {/* Save Button */}
          <div className="flex justify-between items-center pt-4 border-t">
            <div className="text-sm text-gray-600">
              Total configured emails: {emailSettings.esg_emails.length + emailSettings.credit_rating_emails.length}
            </div>
            <button
              onClick={saveEmailSettings}
              disabled={isSaving}
              className="flex items-center px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
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
              <Loader className="h-6 w-6 text-blue-500 animate-spin" />
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
            <Loader className="h-8 w-8 text-blue-500 animate-spin" />
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
                <div className="bg-blue-50 p-3 rounded-lg">
                  <div className="text-sm text-gray-600">Total Pages</div>
                  <div className="text-xl font-semibold">{systemStatus.database?.total_pages || 0}</div>
                </div>
                <div className="bg-green-50 p-3 rounded-lg">
                  <div className="text-sm text-gray-600">Active Pages</div>
                  <div className="text-xl font-semibold">{systemStatus.database?.active_pages || 0}</div>
                </div>
                <div className="bg-purple-50 p-3 rounded-lg">
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
      
      {/* Extraction Schedule */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
          <Clock className="h-5 w-5 mr-2" />
          Extraction Schedule
        </h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Extraction Frequency
            </label>
            <select className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50">
              <option>Every 3 hours</option>
              <option>Every 6 hours</option>
              <option>Every 12 hours</option>
              <option>Every 24 hours</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Last Extraction
            </label>
            <input
              type="text"
              value={systemStatus?.recent_activity && systemStatus.recent_activity.length > 0 
                ? new Date(systemStatus.recent_activity[0].started_at).toLocaleString() 
                : 'No recent extraction'}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50"
              disabled
            />
          </div>
          <button className="mt-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors">
            Save Schedule
          </button>
        </div>
      </div>

      {/* Database Settings */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
          <Database className="h-5 w-5 mr-2" />
          Database Management
        </h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Database Location
            </label>
            <input
              type="text"
              value="./data/tender_monitoring.db"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50"
              disabled
            />
          </div>
          <div className="flex gap-3">
            <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
              Backup Database
            </button>
            <button className="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700 transition-colors">
              Clean Old Records
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};