import React, { useState } from 'react';
import { Plus, Tag, Trash2, Filter } from 'lucide-react';
import { Keyword, CategoryType } from '../types';
import { apiService } from '../services/api';

interface KeywordManagerProps {
  keywords: Keyword[];
  onRefresh: () => void;
}

export const KeywordManager: React.FC<KeywordManagerProps> = ({ keywords, onRefresh }) => {
  const [showAddForm, setShowAddForm] = useState(false);
  const [newKeyword, setNewKeyword] = useState({ keyword: '', category: 'esg' as 'esg' | 'credit_rating' });
  const [filterCategory, setFilterCategory] = useState<CategoryType>('all');

  const handleAddKeyword = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiService.createKeyword(newKeyword);
      setNewKeyword({ keyword: '', category: 'esg' });
      setShowAddForm(false);
      onRefresh();
    } catch (error) {
      console.error('Failed to add keyword:', error);
    }
  };

  const handleDeleteKeyword = async (id: number) => {
    if (window.confirm('Are you sure you want to delete this keyword?')) {
      try {
        await apiService.deleteKeyword(id);
        onRefresh();
      } catch (error) {
        console.error('Failed to delete keyword:', error);
      }
    }
  };

  const filteredKeywords = keywords.filter(keyword => 
    filterCategory === 'all' || keyword.category === filterCategory
  );

  const getCategoryColor = (category: string) => {
    return category === 'esg' 
      ? 'bg-green-100 text-green-800' 
      : 'bg-purple-100 text-purple-800';
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  const esgKeywords = keywords.filter(k => k.category === 'esg');
  const creditKeywords = keywords.filter(k => k.category === 'credit_rating');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-gray-900">Keyword Management</h2>
        <button
          onClick={() => setShowAddForm(true)}
          className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="h-4 w-4 mr-2" />
          Add Keyword
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">ESG Keywords</p>
              <p className="text-2xl font-bold text-green-600 mt-1">{esgKeywords.length}</p>
            </div>
            <div className="p-3 rounded-full bg-green-500">
              <Tag className="h-6 w-6 text-white" />
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Credit Rating Keywords</p>
              <p className="text-2xl font-bold text-purple-600 mt-1">{creditKeywords.length}</p>
            </div>
            <div className="p-3 rounded-full bg-purple-500">
              <Tag className="h-6 w-6 text-white" />
            </div>
          </div>
        </div>
      </div>

      {/* Add Keyword Form */}
      {showAddForm && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Add New Keyword</h3>
          <form onSubmit={handleAddKeyword} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Keyword
              </label>
              <input
                type="text"
                value={newKeyword.keyword}
                onChange={(e) => setNewKeyword({ ...newKeyword, keyword: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="e.g., sustainability, carbon neutral"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Category
              </label>
              <select
                value={newKeyword.category}
                onChange={(e) => setNewKeyword({ ...newKeyword, category: e.target.value as 'esg' | 'credit_rating' })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="esg">ESG</option>
                <option value="credit_rating">Credit Rating</option>
              </select>
            </div>
            <div className="flex gap-3">
              <button
                type="submit"
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                Add Keyword
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowAddForm(false);
                  setNewKeyword({ keyword: '', category: 'esg' });
                }}
                className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400 transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Filter */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
        <div className="flex items-center gap-4">
          <Filter className="h-4 w-4 text-gray-400" />
          <select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value as CategoryType)}
            className="px-3 py-1 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            <option value="all">All Categories</option>
            <option value="esg">ESG</option>
            <option value="credit_rating">Credit Rating</option>
          </select>
        </div>
      </div>

      {/* Keywords List */}
      <div className="space-y-4">
        {filteredKeywords.length === 0 ? (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center">
            <Tag className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-500">No keywords found.</p>
            <p className="text-sm text-gray-400 mt-1">Add keywords to help categorize tenders.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredKeywords.map((keyword) => (
              <div key={keyword.id} className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${getCategoryColor(keyword.category)}`}>
                    {keyword.category === 'esg' ? 'ESG' : 'Credit Rating'}
                  </span>
                  <button
                    onClick={() => handleDeleteKeyword(keyword.id)}
                    className="p-1 text-red-600 hover:bg-red-50 rounded transition-colors"
                    title="Delete"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <h3 className="font-medium text-gray-900 mb-1">{keyword.keyword}</h3>
                <p className="text-xs text-gray-500">
                  Added: {formatDate(keyword.created_at)}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Results Summary */}
      <div className="text-center text-sm text-gray-500">
        Showing {filteredKeywords.length} of {keywords.length} keywords
      </div>
    </div>
  );
};
