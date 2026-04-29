import React, { useState } from 'react';
import { Plus, Globe, Edit, Trash2, Power, PowerOff } from 'lucide-react';
import { Page } from '../types';
import { apiService } from '../services/api';

interface PageManagerProps {
  pages: Page[];
  onRefresh: () => void;
}

export const PageManager: React.FC<PageManagerProps> = ({ pages, onRefresh }) => {
  const [showAddForm, setShowAddForm] = useState(false);
  const [newPage, setNewPage] = useState({ url: '', name: '' });
  const [editingPage, setEditingPage] = useState<Page | null>(null);

  const handleAddPage = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiService.createPage(newPage);
      setNewPage({ url: '', name: '' });
      setShowAddForm(false);
      onRefresh();
    } catch (error) {
      console.error('Failed to add page:', error);
    }
  };

  const handleUpdatePage = async (page: Page) => {
    try {
      await apiService.updatePage(page.id, { is_active: !page.is_active });
      onRefresh();
    } catch (error) {
      console.error('Failed to update page:', error);
    }
  };

  const handleDeletePage = async (id: number) => {
    if (window.confirm('Are you sure you want to delete this page?')) {
      try {
        await apiService.deletePage(id);
        onRefresh();
      } catch (error) {
        console.error('Failed to delete page:', error);
      }
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-gray-900">Page Management</h2>
        <button
          onClick={() => setShowAddForm(true)}
          className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="h-4 w-4 mr-2" />
          Add Page
        </button>
      </div>

      {/* Add Page Form */}
      {showAddForm && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Add New Page</h3>
          <form onSubmit={handleAddPage} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Page Name
              </label>
              <input
                type="text"
                value={newPage.name}
                onChange={(e) => setNewPage({ ...newPage, name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="e.g., Uzbekistan Airways Tenders"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                URL
              </label>
              <input
                type="url"
                value={newPage.url}
                onChange={(e) => setNewPage({ ...newPage, url: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="https://example.com/tenders"
                required
              />
            </div>
            <div className="flex gap-3">
              <button
                type="submit"
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                Add Page
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowAddForm(false);
                  setNewPage({ url: '', name: '' });
                }}
                className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400 transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Pages List */}
      <div className="space-y-4">
        {pages.length === 0 ? (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center">
            <Globe className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-500">No pages configured yet.</p>
            <p className="text-sm text-gray-400 mt-1">Add your first page to start monitoring tenders.</p>
          </div>
        ) : (
          pages.map((page) => (
            <div key={page.id} className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <div className="flex items-center justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-lg font-semibold text-gray-900">{page.name}</h3>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                      page.is_active 
                        ? 'bg-green-100 text-green-800' 
                        : 'bg-gray-100 text-gray-800'
                    }`}>
                      {page.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 mb-2 break-all">{page.url}</p>
                  <p className="text-xs text-gray-500">
                    Added: {formatDate(page.created_at)}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => handleUpdatePage(page)}
                    className={`p-2 rounded-lg transition-colors ${
                      page.is_active
                        ? 'text-red-600 hover:bg-red-50'
                        : 'text-green-600 hover:bg-green-50'
                    }`}
                    title={page.is_active ? 'Deactivate' : 'Activate'}
                  >
                    {page.is_active ? <PowerOff className="h-4 w-4" /> : <Power className="h-4 w-4" />}
                  </button>
                  <button
                    onClick={() => handleDeletePage(page.id)}
                    className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                    title="Delete"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
