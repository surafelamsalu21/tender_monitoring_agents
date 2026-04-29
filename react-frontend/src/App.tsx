// App.tsx - Updated to include Test Crawler tab
import React, { useState } from 'react';
import { 
  LayoutDashboard, 
  FileText, 
  Globe, 
  Tag, 
  Settings as SettingsIcon,
  TestTube
} from 'lucide-react';
import { useApiData } from './hooks/useApi';
import { 
  Dashboard, 
  TenderList, 
  PageManager, 
  KeywordManager, 
  Settings,
  TestCrawler 
} from './components';
import { TabType } from './types';

function App() {
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');
  
  const {
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
  } = useApiData();

  const refreshData = async () => {
    await Promise.all([loadTenders(), loadPages(), loadKeywords()]);
  };

  const navigation = [
    { id: 'dashboard', name: 'Dashboard', icon: LayoutDashboard },
    { id: 'tenders', name: 'Tenders', icon: FileText },
    { id: 'pages', name: 'Pages', icon: Globe },
    { id: 'keywords', name: 'Keywords', icon: Tag },
    { id: 'test-crawler', name: 'Test Crawler', icon: TestTube }, // NEW TAB
    { id: 'settings', name: 'Settings', icon: SettingsIcon },
  ];

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return (
          <Dashboard 
            stats={stats}
            systemStatus={systemStatus}
            tenders={tenders}
            onTriggerExtraction={triggerExtraction}
          />
        );
      case 'tenders':
        return <TenderList tenders={tenders} />;
      case 'pages':
        return <PageManager pages={pages} onRefresh={refreshData} />;
      case 'keywords':
        return <KeywordManager keywords={keywords} onRefresh={refreshData} />;
      case 'test-crawler': // NEW CASE
        return <TestCrawler onRefresh={refreshData} />;
      case 'settings':
        return <Settings />;
      default:
        return (
          <Dashboard 
            stats={stats} 
            systemStatus={systemStatus} 
            tenders={tenders}
            onTriggerExtraction={triggerExtraction} 
          />
        );
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header with Navigation Tabs */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-6">
          {/* Top bar with title */}
          <div className="flex items-center justify-between h-16 border-b border-gray-100">
            <div className="flex items-center">
              <h1 className="text-2xl font-bold text-gray-900">Tender Monitor</h1>
              {/* Show processing indicator */}
              {tenders.length > 0 && (
                <div className="ml-6 flex items-center text-sm text-gray-500">
                  <div className="w-2 h-2 bg-green-500 rounded-full mr-2 animate-pulse"></div>
                  AI Agents Active
                </div>
              )}
            </div>
            
            {error && (
              <div className="flex items-center">
                <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-2 rounded-lg text-sm">
                  {error}
                  <button 
                    onClick={() => setError(null)}
                    className="ml-2 text-red-500 hover:text-red-700"
                  >
                    ×
                  </button>
                </div>
              </div>
            )}
          </div>
          
          {/* Navigation Tabs */}
          <nav className="flex space-x-8 py-4">
            {navigation.map((item) => {
              const Icon = item.icon;
              // Add badge for tenders tab to show processed count
              const showBadge = item.id === 'tenders' && tenders.filter(t => t.is_processed).length > 0;
              // Add special styling for test crawler tab
              const isTestCrawler = item.id === 'test-crawler';
              
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id as TabType)}
                  className={`flex items-center px-4 py-2 text-sm font-medium rounded-lg transition-colors relative ${
                    activeTab === item.id
                      ? isTestCrawler 
                        ? 'bg-purple-100 text-purple-700 border-2 border-purple-200'
                        : 'bg-blue-100 text-blue-700 border-2 border-blue-200'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 border-2 border-transparent'
                  }`}
                >
                  <Icon className={`h-5 w-5 mr-2 ${isTestCrawler ? 'text-purple-600' : ''}`} />
                  {item.name}
                  {showBadge && (
                    <span className="ml-2 bg-green-500 text-white text-xs px-2 py-0.5 rounded-full">
                      {tenders.filter(t => t.is_processed).length}
                    </span>
                  )}
                  {isTestCrawler && activeTab === item.id && (
                    <span className="ml-2 bg-purple-500 text-white text-xs px-2 py-0.5 rounded-full">
                      NEW
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>
      </header>

      {/* Main content */}
      <main className="p-8 max-w-7xl mx-auto">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            <span className="ml-3 text-gray-600">Loading tender data...</span>
          </div>
        ) : (
          renderContent()
        )}
      </main>
    </div>
  );
}

export default App;