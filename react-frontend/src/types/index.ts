// types/index.ts - Updated with Test Crawler tab type
export interface Tender {
  id: number;
  title: string;
  url: string;
  date_published?: string;  // For backward compatibility
  tender_date?: string;    // New field from API
  description?: string;    // Added from API
  category?: string; // legacy field
  source?: string;
  country?: string;
  opportunity_type?: 'grant' | 'consultancy' | 'other' | string;
  estimated_budget?: string;
  screening_version?: string;
  screening_yes_count?: number;
  passes_screening?: boolean;
  screening_step1?: ScreeningStep1;
  screening_step2?: ScreeningStep2;
  screening_step3?: ScreeningStep3;
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

export interface ScreeningStep1 {
  mission_alignment?: boolean;
  sector_relevance?: boolean;
  activity_fit?: boolean;
  geographic_fit?: boolean;
  eligibility_quick_check?: boolean;
}

export interface ScreeningStep2 {
  opportunity_characteristics?: string[];
  strategic_signals?: string[];
  potential_concerns?: string[];
  /** ISO-style tag copied from Agent 1 when notice was non-English (fr, mixed, …) */
  source_language?: string;
}

export interface ScreeningStep3 {
  title?: string;
  source?: string;
  country?: string;
  type?: string;
  deadline?: string;
  estimated_budget?: string;
  link?: string;
}

export interface Page {
  id: number;
  url: string;
  name: string;
  is_active: boolean;
  crawl_strategy?: 'crawl4ai' | 'playwright' | 'hybrid';
  created_at: string;
  updated_at: string;
}

export interface Keyword {
  id: number;
  keyword: string;
  category: string;
  created_at: string;
  updated_at: string;
}

export interface Stats {
  total: number;
  /** Strong match — Step 1 yes_count >= 3 */
  recommended: number;
  /** Low match — Step 1 yes_count 1–2 (still visible in list) */
  lowMatch: number;
  pages: number;
}

export interface SystemStatus {
  status: string;
  message: string;
}

export type TabType =
  | 'dashboard'
  | 'tenders'
  | 'pages'
  | 'keywords'
  | 'test-crawler'
  | 'settings'
  | 'account';
export type CategoryType = 'all' | 'passed' | 'failed';