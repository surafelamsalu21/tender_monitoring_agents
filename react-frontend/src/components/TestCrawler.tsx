// components/TestCrawler.tsx - New Test Crawler Component
import React, { useState } from 'react';
import { 
  Search, 
  Play, 
  CheckCircle, 
  AlertCircle, 
  Loader, 
  ExternalLink, 
  Plus,
  Eye,
  EyeOff,
  Globe,
  FileText,
  Link,
  Clock
} from 'lucide-react';
import { apiService } from '../services/api';

interface CrawlResult {
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

interface TestCrawlerProps {
  onRefresh?: () => void;
}

export const TestCrawler: React.FC<TestCrawlerProps> = ({ onRefresh }) => {
  const [testUrl, setTestUrl] = useState('');
  const [testing, setTesting] = useState(false);
  const [crawlResult, setCrawlResult] = useState<CrawlResult | null>(null);
  const [showMarkdown, setShowMarkdown] = useState(true);
  const [showMetadata, setShowMetadata] = useState(false);
  const [addingToPages, setAddingToPages] = useState(false);
  const [pageName, setPageName] = useState('');

  const isValidUrl = (url: string): boolean => {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  };

  const testCrawler = async () => {
    if (!testUrl.trim()) {
      alert('Please enter a URL to test');
      return;
    }

    if (!isValidUrl(testUrl)) {
      alert('Please enter a valid URL (including http:// or https://)');
      return;
    }

    setTesting(true);
    setCrawlResult(null);
    
    try {
      // Call the test crawler API endpoint
      const result = await apiService.testCrawler(testUrl);
      setCrawlResult(result);
      
      // Auto-generate page name from title or URL
      if (result.status === 'success' && result.title) {
        setPageName(result.title);
      } else {
        // Generate name from URL
        const urlObj = new URL(testUrl);
        setPageName(`${urlObj.hostname} - Tender Page`);
      }
    } catch (error) {
      console.error('Test crawler error:', error);
      setCrawlResult({
        status: 'error',
        url: testUrl,
        error: 'Failed to test crawler. Please check your connection and try again.'
      });
    } finally {
      setTesting(false);
    }
  };

  const addToPages = async () => {
    if (!crawlResult || crawlResult.status !== 'success') {
      alert('Cannot add page - crawling was not successful');
      return;
    }

    if (!pageName.trim()) {
      alert('Please enter a name for the page');
      return;
    }

    setAddingToPages(true);
    try {
      await apiService.createPage({
        url: testUrl,
        name: pageName.trim()
      });
      
      alert(`Successfully added "${pageName}" to monitored pages!`);
      
      // Reset form
      setTestUrl('');
      setPageName('');
      setCrawlResult(null);
      
      // Refresh pages list if callback provided
      if (onRefresh) {
        onRefresh();
      }
    } catch (error) {
      console.error('Failed to add page:', error);
      alert('Failed to add page. It may already exist or there was a server error.');
    } finally {
      setAddingToPages(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const truncateText = (text: string, maxLength: number): string => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  // Simple markdown to HTML parser for basic rendering
  const parseMarkdownToHTML = (markdown: string): string => {
    if (!markdown) return '<p class="text-gray-500">No content available</p>';
    
    let html = markdown
      // Convert headers
      .replace(/^### (.*$)/gim, '<h3 class="text-lg font-semibold text-gray-900 mt-4 mb-2">$1</h3>')
      .replace(/^## (.*$)/gim, '<h2 class="text-xl font-semibold text-gray-900 mt-6 mb-3">$1</h2>')
      .replace(/^# (.*$)/gim, '<h1 class="text-2xl font-bold text-gray-900 mt-8 mb-4">$1</h1>')
      
      // Convert bold and italic
      .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-gray-900">$1</strong>')
      .replace(/\*(.*?)\*/g, '<em class="italic text-gray-700">$1</em>')
      
      // Convert links
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="text-blue-600 hover:text-blue-800 underline" target="_blank" rel="noopener noreferrer">$1</a>')
      
      // Convert inline code
      .replace(/`([^`]+)`/g, '<code class="bg-gray-100 text-gray-800 px-1 py-0.5 rounded text-sm font-mono">$1</code>')
      
      // Convert line breaks
      .replace(/\n\n/g, '</p><p class="mb-3 text-gray-700 leading-relaxed">')
      .replace(/\n/g, '<br/>');
    
    // Handle lists
    html = html.replace(/^[\s]*[\*\-\+] (.*)$/gm, '<li class="ml-4 mb-1 text-gray-700">• $1</li>');
    
    // Wrap in paragraphs if not already wrapped
    if (!html.includes('<p>') && !html.includes('<h1>') && !html.includes('<h2>') && !html.includes('<h3>')) {
      html = `<p class="mb-3 text-gray-700 leading-relaxed">${html}</p>`;
    } else {
      // Ensure first content is wrapped in paragraph
      if (!html.startsWith('<')) {
        html = `<p class="mb-3 text-gray-700 leading-relaxed">${html}`;
      }
    }
    
    // Clean up empty paragraphs and add proper spacing
    html = html
      .replace(/<p class="mb-3 text-gray-700 leading-relaxed"><\/p>/g, '')
      .replace(/<p class="mb-3 text-gray-700 leading-relaxed">/g, '<p class="mb-3 text-gray-700 leading-relaxed">')
      .replace(/(<\/p>)/g, '</p>');
    
    return html;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Test Crawler</h1>
        <p className="text-gray-600">Test if crawl4ai can extract content from a webpage before adding it to monitored pages</p>
      </div>

      {/* Test URL Input */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
          <Search className="h-5 w-5 mr-2" />
          Test URL
        </h3>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Enter URL to test
            </label>
            <div className="flex gap-3">
              <div className="flex-1">
                <input
                  type="url"
                  value={testUrl}
                  onChange={(e) => setTestUrl(e.target.value)}
                  onKeyPress={(e) => {
                    if (e.key === 'Enter' && !testing) {
                      testCrawler();
                    }
                  }}
                  placeholder="https://example.com/tenders"
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                  disabled={testing}
                />
              </div>
              <button
                onClick={testCrawler}
                disabled={testing || !testUrl.trim()}
                className="flex items-center px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {testing ? (
                  <>
                    <Loader className="h-5 w-5 mr-2 animate-spin" />
                    Testing...
                  </>
                ) : (
                  <>
                    <Play className="h-5 w-5 mr-2" />
                    Test Crawler
                  </>
                )}
              </button>
            </div>
          </div>
          
          {/* Quick Test URLs */}
          <div className="flex flex-wrap gap-2">
            <span className="text-sm text-gray-500">Quick test:</span>
            {[
              'https://corp.uzairways.com/ru/press-center/tenders',
              'https://example.com/tenders'
            ].map((url, index) => (
              <button
                key={index}
                onClick={() => setTestUrl(url)}
                disabled={testing}
                className="text-xs px-2 py-1 bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition-colors disabled:opacity-50"
              >
                {new URL(url).hostname}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Crawl Results */}
      {crawlResult && (
        <div className="space-y-6">
          {/* Status Summary */}
          <div className={`rounded-xl shadow-sm border p-6 ${
            crawlResult.status === 'success' 
              ? 'bg-green-50 border-green-200' 
              : 'bg-red-50 border-red-200'
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                {crawlResult.status === 'success' ? (
                  <CheckCircle className="h-6 w-6 text-green-600 mr-3" />
                ) : (
                  <AlertCircle className="h-6 w-6 text-red-600 mr-3" />
                )}
                <div>
                  <h3 className={`text-lg font-semibold ${
                    crawlResult.status === 'success' ? 'text-green-900' : 'text-red-900'
                  }`}>
                    {crawlResult.status === 'success' ? 'Crawling Successful!' : 'Crawling Failed'}
                  </h3>
                  <p className={`text-sm ${
                    crawlResult.status === 'success' ? 'text-green-700' : 'text-red-700'
                  }`}>
                    {crawlResult.status === 'success' 
                      ? 'Content extracted successfully. You can now add this page to monitoring.'
                      : crawlResult.error || 'Failed to extract content from the page.'
                    }
                  </p>
                </div>
              </div>
              
              {crawlResult.status === 'success' && (
                <a
                  href={crawlResult.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center px-3 py-2 text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded-lg transition-colors"
                >
                  <ExternalLink className="h-4 w-4 mr-1" />
                  Visit Page
                </a>
              )}
            </div>
          </div>

          {/* Success Results */}
          {crawlResult.status === 'success' && (
            <>
              {/* Metadata */}
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-gray-900 flex items-center">
                    <Globe className="h-5 w-5 mr-2" />
                    Page Information
                  </h3>
                  <button
                    onClick={() => setShowMetadata(!showMetadata)}
                    className="flex items-center px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition-colors"
                  >
                    {showMetadata ? <EyeOff className="h-4 w-4 mr-1" /> : <Eye className="h-4 w-4 mr-1" />}
                    {showMetadata ? 'Hide Details' : 'Show Details'}
                  </button>
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                  <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
                    <div className="flex items-center mb-2">
                      <FileText className="h-5 w-5 text-blue-600 mr-2" />
                      <span className="font-semibold text-blue-900">Content</span>
                    </div>
                    <p className="text-blue-800 text-sm">
                      {crawlResult.word_count || 0} words, {formatFileSize(crawlResult.char_count || 0)}
                    </p>
                  </div>
                  
                  <div className="bg-green-50 p-4 rounded-lg border border-green-200">
                    <div className="flex items-center mb-2">
                      <Link className="h-5 w-5 text-green-600 mr-2" />
                      <span className="font-semibold text-green-900">Links</span>
                    </div>
                    <p className="text-green-800 text-sm">
                      {crawlResult.links?.length || 0} links found
                    </p>
                  </div>
                  
                  <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
                    <div className="flex items-center mb-2">
                      <Clock className="h-5 w-5 text-purple-600 mr-2" />
                      <span className="font-semibold text-purple-900">Status</span>
                    </div>
                    <p className="text-purple-800 text-sm">Ready to monitor</p>
                  </div>
                </div>

                {/* Page Details */}
                <div className="space-y-3">
                  <div>
                    <label className="text-sm font-medium text-gray-600">Page Title:</label>
                    <p className="text-gray-900">{crawlResult.title || 'No title found'}</p>
                  </div>
                  <div>
                    <label className="text-sm font-medium text-gray-600">URL:</label>
                    <p className="text-gray-900 break-all">{crawlResult.url}</p>
                  </div>
                </div>

                {/* Metadata Details */}
                {showMetadata && crawlResult.metadata && (
                  <div className="mt-4 p-4 bg-gray-50 rounded-lg">
                    <h4 className="font-medium text-gray-800 mb-2">Technical Details:</h4>
                    <pre className="text-xs text-gray-600 overflow-x-auto">
                      {JSON.stringify(crawlResult.metadata, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              {/* Content Preview */}
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-gray-900 flex items-center">
                    <FileText className="h-5 w-5 mr-2" />
                    Content Preview
                  </h3>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setShowMarkdown(true)}
                      className={`px-3 py-1 text-sm rounded transition-colors ${
                        showMarkdown 
                          ? 'bg-blue-600 text-white' 
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      Rendered
                    </button>
                    <button
                      onClick={() => setShowMarkdown(false)}
                      className={`px-3 py-1 text-sm rounded transition-colors ${
                        !showMarkdown 
                          ? 'bg-blue-600 text-white' 
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      Raw
                    </button>
                  </div>
                </div>
                
                <div className="bg-gray-50 rounded-lg p-4 max-h-96 overflow-y-auto">
                  {showMarkdown ? (
                    // Rendered Markdown Content
                    <div 
                      className="prose prose-sm max-w-none text-gray-800"
                      dangerouslySetInnerHTML={{ 
                        __html: crawlResult.markdown 
                          ? parseMarkdownToHTML(crawlResult.markdown)
                          : '<p class="text-gray-500">No content available</p>'
                      }}
                    />
                  ) : (
                    // Raw Content
                    <pre className="text-sm text-gray-800 whitespace-pre-wrap break-words">
                      {crawlResult.html ? truncateText(crawlResult.html, 5000) : 'No HTML content available'}
                    </pre>
                  )}
                </div>
                
                {crawlResult.markdown && crawlResult.markdown.length > 10000 && (
                  <p className="text-sm text-gray-500 mt-2">
                    Content truncated for display. Full content will be used for monitoring.
                  </p>
                )}
              </div>

              {/* Add to Pages Section */}
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                  <Plus className="h-5 w-5 mr-2" />
                  Add to Monitored Pages
                </h3>
                
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Page Name
                    </label>
                    <input
                      type="text"
                      value={pageName}
                      onChange={(e) => setPageName(e.target.value)}
                      placeholder="Enter a descriptive name for this page"
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                    />
                  </div>
                  
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-gray-600">
                      This will add the page to your monitored pages list and start extracting tenders from it.
                    </div>
                    <button
                      onClick={addToPages}
                      disabled={addingToPages || !pageName.trim()}
                      className="flex items-center px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {addingToPages ? (
                        <>
                          <Loader className="h-5 w-5 mr-2 animate-spin" />
                          Adding...
                        </>
                      ) : (
                        <>
                          <Plus className="h-5 w-5 mr-2" />
                          Add to Pages
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Help Section */}
      {!crawlResult && (
        <div className="bg-blue-50 rounded-xl border border-blue-200 p-6">
          <h3 className="text-lg font-semibold text-blue-900 mb-3">How to Use Test Crawler</h3>
          <div className="space-y-2 text-blue-800">
            <p>1. Enter the URL of a tender/procurement page you want to monitor</p>
            <p>2. Click "Test Crawler" to see if crawl4ai can extract content successfully</p>
            <p>3. Review the extracted content to ensure it contains tender information</p>
            <p>4. If successful, give the page a descriptive name and click "Add to Pages"</p>
          </div>
          <div className="mt-4 p-3 bg-blue-100 rounded-lg">
            <p className="text-sm text-blue-700">
              <strong>Tip:</strong> Look for pages that contain lists of tenders, procurement opportunities, or bidding information. 
              The crawler works best with well-structured HTML pages.
            </p>
          </div>
        </div>
      )}
    </div>
  );
};