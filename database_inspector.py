"""
SQLite Database Inspector
Tool to check what data the agents are saving to the database
"""
import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Any
import pandas as pd
from pathlib import Path

class DatabaseInspector:
    """Inspect SQLite database to see what agents are saving"""
    
    def __init__(self, db_path: str = "tender_monitoring.db"):
        self.db_path = db_path
        self.conn = None
    
    def connect(self):
        """Connect to the SQLite database"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # Enable column access by name
            print(f"✅ Connected to database: {self.db_path}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to database: {e}")
            return False
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("📤 Database connection closed")
    
    def get_all_tables(self) -> List[str]:
        """Get list of all tables in the database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            return tables
        except Exception as e:
            print(f"❌ Error getting tables: {e}")
            return []
    
    def get_table_schema(self, table_name: str) -> List[Dict]:
        """Get schema/structure of a table"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            
            schema = []
            for col in columns:
                schema.append({
                    'column_id': col[0],
                    'name': col[1],
                    'type': col[2],
                    'not_null': bool(col[3]),
                    'default': col[4],
                    'primary_key': bool(col[5])
                })
            return schema
        except Exception as e:
            print(f"❌ Error getting schema for {table_name}: {e}")
            return []
    
    def get_table_count(self, table_name: str) -> int:
        """Get row count for a table"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            return cursor.fetchone()[0]
        except Exception as e:
            print(f"❌ Error counting rows in {table_name}: {e}")
            return 0
    
    def inspect_all_tables(self):
        """Print overview of all tables"""
        print("\n" + "="*60)
        print("🔍 DATABASE OVERVIEW")
        print("="*60)
        
        tables = self.get_all_tables()
        if not tables:
            print("❌ No tables found in database")
            return
        
        for table in tables:
            count = self.get_table_count(table)
            print(f"📋 Table: {table:<20} | Rows: {count:>5}")
        
        print("="*60)
    
    def inspect_tenders_table(self, limit: int = 10):
        """Inspect the tenders table (Agent 1 data)"""
        print("\n" + "="*60)
        print("🤖 AGENT 1 DATA - TENDERS TABLE")
        print("="*60)
        
        try:
            # Get schema
            schema = self.get_table_schema('tenders')
            print("\n📊 Table Structure:")
            for col in schema:
                pk = " (PK)" if col['primary_key'] else ""
                nn = " NOT NULL" if col['not_null'] else ""
                print(f"   {col['name']:<20} | {col['type']:<15} {pk}{nn}")
            
            # Get recent data
            cursor = self.conn.cursor()
            cursor.execute(f"""
                SELECT id, title, url, category, tender_date, 
                       is_processed, is_notified, created_at, page_id
                FROM tenders 
                ORDER BY created_at DESC 
                LIMIT {limit}
            """)
            
            rows = cursor.fetchall()
            
            print(f"\n📋 Recent Tenders (Last {limit}):")
            if not rows:
                print("   ❌ No tenders found")
                return
            
            for row in rows:
                print(f"\n   ID: {row['id']}")
                print(f"   Title: {row['title'][:60]}{'...' if len(row['title']) > 60 else ''}")
                print(f"   Category: {row['category']}")
                print(f"   URL: {row['url'][:50]}{'...' if len(row['url']) > 50 else ''}")
                print(f"   Date: {row['tender_date']}")
                print(f"   Processed: {row['is_processed']} | Notified: {row['is_notified']}")
                print(f"   Created: {row['created_at']}")
                print(f"   Page ID: {row['page_id']}")
                print("   " + "-"*50)
            
        except Exception as e:
            print(f"❌ Error inspecting tenders table: {e}")
    
    def inspect_detailed_tenders_table(self, limit: int = 10):
        """Inspect the detailed_tenders table (Agent 2 data)"""
        print("\n" + "="*60)
        print("🤖 AGENT 2 DATA - DETAILED_TENDERS TABLE")
        print("="*60)
        
        try:
            # Get schema
            schema = self.get_table_schema('detailed_tenders')
            print("\n📊 Table Structure:")
            for col in schema:
                pk = " (PK)" if col['primary_key'] else ""
                nn = " NOT NULL" if col['not_null'] else ""
                print(f"   {col['name']:<25} | {col['type']:<15} {pk}{nn}")
            
            # Get recent data with tender info
            cursor = self.conn.cursor()
            cursor.execute(f"""
                SELECT dt.id, dt.tender_id, dt.detailed_title, dt.detailed_description, 
                       dt.requirements, dt.deadline, dt.contact_info, dt.processing_status,
                       dt.created_at, t.title as basic_title, t.category
                FROM detailed_tenders dt
                LEFT JOIN tenders t ON dt.tender_id = t.id
                ORDER BY dt.created_at DESC 
                LIMIT {limit}
            """)
            
            rows = cursor.fetchall()
            
            print(f"\n📋 Recent Detailed Tenders (Last {limit}):")
            if not rows:
                print("   ❌ No detailed tenders found")
                return
            
            for row in rows:
                print(f"\n   Detail ID: {row['id']} | Tender ID: {row['tender_id']}")
                print(f"   Basic Title: {row['basic_title'][:50]}{'...' if row['basic_title'] and len(row['basic_title']) > 50 else ''}")
                print(f"   Detailed Title: {row['detailed_title'][:50]}{'...' if row['detailed_title'] and len(row['detailed_title']) > 50 else ''}")
                print(f"   Category: {row['category']}")
                print(f"   Status: {row['processing_status']}")
                print(f"   Deadline: {row['deadline']}")
                
                # Show requirements (truncated)
                req = row['requirements']
                if req:
                    req_preview = req[:100] + "..." if len(req) > 100 else req
                    print(f"   Requirements: {req_preview}")
                
                # Show contact info (parsed if JSON)
                contact = row['contact_info']
                if contact:
                    try:
                        contact_data = json.loads(contact)
                        org = contact_data.get('organization', 'N/A')
                        person = contact_data.get('contact_person', 'N/A')
                        print(f"   Contact: {org} - {person}")
                    except:
                        print(f"   Contact: {contact[:50]}...")
                
                print(f"   Created: {row['created_at']}")
                print("   " + "-"*50)
            
        except Exception as e:
            print(f"❌ Error inspecting detailed_tenders table: {e}")
    
    def inspect_pages_table(self):
        """Inspect monitored pages"""
        print("\n" + "="*60)
        print("📄 MONITORED PAGES")
        print("="*60)
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, name, url, is_active, last_crawled, 
                       consecutive_failures, created_at
                FROM monitored_pages
                ORDER BY created_at DESC
            """)
            
            rows = cursor.fetchall()
            
            if not rows:
                print("   ❌ No monitored pages found")
                return
            
            for row in rows:
                status = "🟢 Active" if row['is_active'] else "🔴 Inactive"
                print(f"\n   ID: {row['id']} | {status}")
                print(f"   Name: {row['name']}")
                print(f"   URL: {row['url']}")
                print(f"   Last Crawled: {row['last_crawled']}")
                print(f"   Failures: {row['consecutive_failures']}")
                print(f"   Created: {row['created_at']}")
                print("   " + "-"*50)
            
        except Exception as e:
            print(f"❌ Error inspecting pages table: {e}")
    
    def inspect_keywords_table(self):
        """Inspect keywords"""
        print("\n" + "="*60)
        print("🏷️ KEYWORDS")
        print("="*60)
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT category, keyword, is_active, created_at
                FROM keywords
                ORDER BY category, keyword
            """)
            
            rows = cursor.fetchall()
            
            if not rows:
                print("   ❌ No keywords found")
                return
            
            # Group by category
            current_category = None
            for row in rows:
                if current_category != row['category']:
                    current_category = row['category']
                    print(f"\n   📂 {current_category.upper()} Keywords:")
                
                status = "✅" if row['is_active'] else "❌"
                print(f"      {status} {row['keyword']}")
            
        except Exception as e:
            print(f"❌ Error inspecting keywords table: {e}")
    
    def inspect_crawl_logs(self, limit: int = 10):
        """Inspect crawl logs"""
        print("\n" + "="*60)
        print("📊 CRAWL LOGS")
        print("="*60)
        
        try:
            cursor = self.conn.cursor()
            cursor.execute(f"""
                SELECT cl.id, cl.page_id, cl.status, cl.tenders_found, 
                       cl.started_at, cl.completed_at, cl.error_message,
                       mp.name as page_name
                FROM crawl_logs cl
                LEFT JOIN monitored_pages mp ON cl.page_id = mp.id
                ORDER BY cl.started_at DESC 
                LIMIT {limit}
            """)
            
            rows = cursor.fetchall()
            
            if not rows:
                print("   ❌ No crawl logs found")
                return
            
            print(f"\n📋 Recent Crawls (Last {limit}):")
            for row in rows:
                status_icon = "✅" if row['status'] == 'completed' else "❌" if row['status'] == 'failed' else "⏳"
                print(f"\n   {status_icon} Log ID: {row['id']}")
                print(f"   Page: {row['page_name']} (ID: {row['page_id']})")
                print(f"   Status: {row['status']}")
                print(f"   Tenders Found: {row['tenders_found']}")
                print(f"   Started: {row['started_at']}")
                print(f"   Completed: {row['completed_at']}")
                if row['error_message']:
                    print(f"   Error: {row['error_message'][:100]}...")
                print("   " + "-"*50)
            
        except Exception as e:
            print(f"❌ Error inspecting crawl logs: {e}")
    
    def get_pipeline_summary(self):
        """Get a summary of the entire pipeline data"""
        print("\n" + "="*60)
        print("🎯 PIPELINE SUMMARY")
        print("="*60)
        
        try:
            cursor = self.conn.cursor()
            
            # Count tenders by category
            cursor.execute("""
                SELECT category, COUNT(*) as count 
                FROM tenders 
                GROUP BY category
            """)
            tender_counts = cursor.fetchall()
            
            # Count processed vs unprocessed
            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN is_processed = 1 THEN 1 ELSE 0 END) as processed,
                    SUM(CASE WHEN is_processed = 0 THEN 1 ELSE 0 END) as unprocessed,
                    SUM(CASE WHEN is_notified = 1 THEN 1 ELSE 0 END) as notified,
                    SUM(CASE WHEN is_notified = 0 THEN 1 ELSE 0 END) as unnotified
                FROM tenders
            """)
            processing_stats = cursor.fetchone()
            
            # Count detailed tenders
            cursor.execute("SELECT COUNT(*) FROM detailed_tenders")
            detailed_count = cursor.fetchone()[0]
            
            # Recent activity
            cursor.execute("""
                SELECT COUNT(*) FROM tenders 
                WHERE created_at >= datetime('now', '-24 hours')
            """)
            recent_tenders = cursor.fetchone()[0]
            
            print("\n📊 Tender Counts by Category:")
            for row in tender_counts:
                print(f"   {row['category']:>15}: {row['count']:>3} tenders")
            
            print(f"\n🔄 Processing Status:")
            print(f"   {'Processed':>15}: {processing_stats['processed']:>3}")
            print(f"   {'Unprocessed':>15}: {processing_stats['unprocessed']:>3}")
            print(f"   {'Notified':>15}: {processing_stats['notified']:>3}")
            print(f"   {'Unnotified':>15}: {processing_stats['unnotified']:>3}")
            
            print(f"\n📋 Pipeline Data:")
            print(f"   {'Basic Tenders':>15}: {self.get_table_count('tenders'):>3} (Agent 1)")
            print(f"   {'Detailed Tenders':>15}: {detailed_count:>3} (Agent 2)")
            print(f"   {'Recent (24h)':>15}: {recent_tenders:>3}")
            
        except Exception as e:
            print(f"❌ Error getting pipeline summary: {e}")
    
    def export_table_to_csv(self, table_name: str, filename: str = None):
        """Export a table to CSV file"""
        if not filename:
            filename = f"{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table_name}", self.conn)
            df.to_csv(filename, index=False)
            print(f"✅ Exported {table_name} to {filename} ({len(df)} rows)")
        except Exception as e:
            print(f"❌ Error exporting {table_name}: {e}")
    
    def run_full_inspection(self):
        """Run complete database inspection"""
        if not self.connect():
            return
        
        try:
            print("🔍 STARTING FULL DATABASE INSPECTION")
            print("="*60)
            
            # Overview
            self.inspect_all_tables()
            
            # Individual table inspections
            self.inspect_pages_table()
            self.inspect_keywords_table()
            self.inspect_tenders_table(5)
            self.inspect_detailed_tenders_table(5)
            self.inspect_crawl_logs(5)
            
            # Summary
            self.get_pipeline_summary()
            
            print("\n✅ INSPECTION COMPLETE")
            print("="*60)
            
        finally:
            self.close()

# Standalone script functions
def quick_inspect():
    """Quick inspection of the database"""
    inspector = DatabaseInspector()
    inspector.run_full_inspection()

def inspect_agents_data():
    """Focus on what agents are saving"""
    inspector = DatabaseInspector()
    if inspector.connect():
        try:
            print("🤖 AGENTS DATA INSPECTION")
            print("="*60)
            inspector.inspect_tenders_table(10)      # Agent 1 data
            inspector.inspect_detailed_tenders_table(10)  # Agent 2 data
            inspector.get_pipeline_summary()
        finally:
            inspector.close()

def inspect_recent_activity():
    """Check recent pipeline activity"""
    inspector = DatabaseInspector()
    if inspector.connect():
        try:
            print("⏰ RECENT ACTIVITY INSPECTION")
            print("="*60)
            inspector.inspect_crawl_logs(10)
            inspector.get_pipeline_summary()
        finally:
            inspector.close()

if __name__ == "__main__":
    # Run full inspection by default
    quick_inspect()