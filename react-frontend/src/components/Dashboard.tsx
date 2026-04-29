// components/Dashboard.tsx - Enhanced with processing information
import React from 'react';
import { 
  FileText, Leaf, CreditCard, Globe, Play, AlertCircle, 
  Bot, Cpu, Database, CheckCircle, Clock 
} from 'lucide-react';
import { StatCard } from './StatCard';
import { Stats, SystemStatus, Tender } from '../types';

interface DashboardProps {
  stats: Stats;
  systemStatus: SystemStatus;
  tenders: Tender[]; // Add tenders to show processing stats
  onTriggerExtraction: () => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ stats, systemStatus, tenders, onTriggerExtraction }) => {
  // Calculate processing statistics
  const processedTenders = tenders.filter(t => t.is_processed);
  const unprocessedTenders = tenders.filter(t => !t.is_processed);
  const notifiedTenders = tenders.filter(t => t.is_notified);
  const unnotifiedTenders = tenders.filter(t => !t.is_notified);
  
  // Recent tenders (last 24 hours)
  const recentTenders = tenders.filter(t => {
    const tenderDate = new Date(t.created_at);
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    return tenderDate > yesterday;
  });

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
          color="bg-blue-500"
          trend={`+${recentTenders.length} today`}
        />
        <StatCard
          title="ESG Tenders"
          value={stats.esg}
          icon={Leaf}
          color="bg-green-500"
          trend={`${Math.round((stats.esg / stats.total * 100) || 0)}% of total`}
        />
        <StatCard
          title="Credit Rating"
          value={stats.credit}
          icon={CreditCard}
          color="bg-purple-500"
          trend={`${Math.round((stats.credit / stats.total * 100) || 0)}% of total`}
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
              <p className="text-2xl font-bold text-blue-600 mt-1">{stats.total}</p>
              <p className="text-xs text-gray-500 mt-1">Basic tender info</p>
            </div>
            <div className="p-3 rounded-full bg-blue-500">
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
              <p className="text-2xl font-bold text-purple-600 mt-1">{notifiedTenders.length}</p>
              <p className="text-xs text-gray-500 mt-1">Email notifications sent</p>
            </div>
            <div className="p-3 rounded-full bg-purple-500">
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
              <div className="w-4 h-4 bg-blue-500 rounded-full mr-2"></div>
              <span className="text-sm text-gray-600">Agent 1: Extract & Categorize</span>
            </div>
            <div className="flex items-center">
              <div className="w-4 h-4 bg-green-500 rounded-full mr-2"></div>
              <span className="text-sm text-gray-600">Agent 2: Detail Extraction</span>
            </div>
            <div className="flex items-center">
              <div className="w-4 h-4 bg-purple-500 rounded-full mr-2"></div>
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
                <span className="font-medium text-purple-600">{notifiedTenders.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Pending Notifications</span>
                <span className="font-medium text-blue-600">{unnotifiedTenders.length}</span>
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
                    className="bg-purple-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${(notifiedTenders.length / stats.total * 100) || 0}%` }}
                  ></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-8">
        <h3 className="text-xl font-semibold text-gray-900 mb-6">Quick Actions</h3>
        <div className="flex flex-wrap gap-4">
          <button
            onClick={onTriggerExtraction}
            className="flex items-center px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium text-base"
          >
            <Play className="h-5 w-5 mr-3" />
            Trigger Manual Extraction
          </button>
        </div>
      </div>

      {/* Recent Activity */}
      <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-8">
        <h3 className="text-xl font-semibold text-gray-900 mb-6">Recent Activity</h3>
        <div className="space-y-4">
          {recentTenders.length > 0 ? (
            recentTenders.slice(0, 5).map((tender, index) => (
              <div key={tender.id} className="flex items-center justify-between py-3 border-b border-gray-100 last:border-b-0">
                <div className="flex items-center">
                  <div className={`w-3 h-3 rounded-full mr-4 ${
                    tender.category === 'esg' ? 'bg-green-500' : 
                    tender.category === 'credit_rating' ? 'bg-purple-500' : 'bg-blue-500'
                  }`}></div>
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      New {tender.category === 'esg' ? 'ESG' : tender.category === 'credit_rating' ? 'Credit Rating' : 'Both'} tender extracted
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
              <p className="text-gray-500">No recent activity</p>
              <p className="text-xs text-gray-400 mt-1">Trigger an extraction to see new tenders</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};