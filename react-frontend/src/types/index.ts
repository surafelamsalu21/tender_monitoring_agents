// types/index.ts - Updated with Test Crawler tab type
export interface Tender {
  id: number;
  title: string;
  url: string;
  date_published?: string;  // For backward compatibility
  tender_date?: string;    // New field from API
  description?: string;    // Added from API
  category: 'esg' | 'credit_rating' | 'both';
  page_id: number;
  page_name?: string;      // Added from API
  is_processed: boolean;   // Added from API
  is_notified: boolean;    // Added from API
  created_at: string;
  updated_at: string;
  detailed_info?: DetailedTenderInfo; // NEW: Detailed information from Agent 2
}

// NEW: Detailed tender information structure
export interface DateValidation {
  urgency_level?: 'urgent' | 'high' | 'medium' | 'low' | 'expired';
  days_until_deadline?: number;
  deadline_status?: 'active' | 'urgent' | 'expired';
  validation_notes?: string[];
}

export interface DetailedTenderInfo {
  detailed_title?: string;
  detailed_description?: string;
  requirements?: string;
  deadline?: string;
  submission_deadline?: string;
  tender_value?: string;
  duration?: string;
  contact_info?: ContactInfo;
  documents_required?: string;
  evaluation_criteria?: string;
  additional_details?: string;
  tender_type?: string;
  procurement_method?: string;
  categories?: string;
  extracted_at?: string;
  page_content_length?: number;
  source_url?: string;
  processing_status?: string;
  error_message?: string;
  // NEW: Date validation information
  date_validation?: {
    deadline_status?: 'active' | 'expired' | 'urgent' | 'unknown';
    days_until_deadline?: number | null;
    urgency_level?: 'low' | 'medium' | 'high' | 'urgent' | 'expired';
    all_extracted_dates?: string[];
    validation_notes?: string[];
  };
}

// NEW: Contact information structure
export interface ContactInfo {
  organization?: string;
  contact_person?: string;
  phone?: string;
  email?: string;
  address?: string;
}

export interface Page {
  id: number;
  url: string;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Keyword {
  id: number;
  keyword: string;
  category: 'esg' | 'credit_rating';
  created_at: string;
  updated_at: string;
}

export interface Stats {
  total: number;
  esg: number;
  credit: number;
  pages: number;
}

export interface SystemStatus {
  status: string;
  message: string;
}

// UPDATED: Added 'test-crawler' to TabType
export type TabType = 'dashboard' | 'tenders' | 'pages' | 'keywords' | 'test-crawler' | 'settings';
export type CategoryType = 'all' | 'esg' | 'credit_rating';