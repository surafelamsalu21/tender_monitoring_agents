#!/usr/bin/env python3
"""
Database Checker Script
Quick script to check what agents are saving to the database
"""
import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from database_inspector import DatabaseInspector, quick_inspect, inspect_agents_data, inspect_recent_activity

def main():
    """Main function with menu options"""
    print("🔍 TENDER AGENT DATABASE INSPECTOR")
    print("="*50)
    print("1. Full Database Inspection")
    print("2. Agents Data Only (What Agent 1 & 2 saved)")
    print("3. Recent Activity Only")
    print("4. Quick Summary")
    print("5. Export Tables to CSV")
    print("="*50)
    
    choice = input("Choose an option (1-5): ").strip()
    
    if choice == "1":
        quick_inspect()
    elif choice == "2":
        inspect_agents_data()
    elif choice == "3":
        inspect_recent_activity()
    elif choice == "4":
        quick_summary()
    elif choice == "5":
        export_menu()
    else:
        print("Invalid choice. Running full inspection...")
        quick_inspect()

def quick_summary():
    """Show just a quick summary"""
    inspector = DatabaseInspector()
    if inspector.connect():
        try:
            inspector.inspect_all_tables()
            inspector.get_pipeline_summary()
        finally:
            inspector.close()

def export_menu():
    """Export tables menu"""
    inspector = DatabaseInspector()
    if inspector.connect():
        try:
            tables = inspector.get_all_tables()
            print("\nAvailable tables:")
            for i, table in enumerate(tables, 1):
                print(f"{i}. {table}")
            
            choice = input(f"\nChoose table to export (1-{len(tables)}): ").strip()
            try:
                table_index = int(choice) - 1
                if 0 <= table_index < len(tables):
                    table_name = tables[table_index]
                    inspector.export_table_to_csv(table_name)
                else:
                    print("Invalid choice")
            except ValueError:
                print("Please enter a number")
        finally:
            inspector.close()

def check_specific_tender(tender_id: int):
    """Check a specific tender by ID"""
    inspector = DatabaseInspector()
    if inspector.connect():
        try:
            cursor = inspector.conn.cursor()
            
            # Get basic tender info
            cursor.execute("SELECT * FROM tenders WHERE id = ?", (tender_id,))
            tender = cursor.fetchone()
            
            if not tender:
                print(f"❌ Tender ID {tender_id} not found")
                return
            
            print(f"🔍 TENDER ID {tender_id} DETAILS")
            print("="*50)
            
            # Basic info
            print("📋 Basic Info (Agent 1):")
            print(f"   Title: {tender['title']}")
            print(f"   URL: {tender['url']}")
            print(f"   Category: {tender['category']}")
            print(f"   Date: {tender['tender_date']}")
            print(f"   Processed: {tender['is_processed']}")
            print(f"   Notified: {tender['is_notified']}")
            print(f"   Created: {tender['created_at']}")
            
            # Detailed info
            cursor.execute("SELECT * FROM detailed_tenders WHERE tender_id = ?", (tender_id,))
            detailed = cursor.fetchone()
            
            if detailed:
                print("\n📊 Detailed Info (Agent 2):")
                print(f"   Detailed Title: {detailed['detailed_title']}")
                print(f"   Requirements: {detailed['requirements'][:100]}...")
                print(f"   Deadline: {detailed['deadline']}")
                print(f"   Contact Info: {detailed['contact_info']}")
                print(f"   Status: {detailed['processing_status']}")
                print(f"   Processed At: {detailed['processed_at']}")
            else:
                print("\n❌ No detailed info found (Agent 2 not processed)")
            
        finally:
            inspector.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--tender" and len(sys.argv) > 2:
            try:
                tender_id = int(sys.argv[2])
                check_specific_tender(tender_id)
            except ValueError:
                print("Please provide a valid tender ID number")
        elif sys.argv[1] == "--agents":
            inspect_agents_data()
        elif sys.argv[1] == "--recent":
            inspect_recent_activity()
        elif sys.argv[1] == "--summary":
            quick_summary()
        else:
            print("Usage:")
            print("  python check_db.py                 # Interactive menu")
            print("  python check_db.py --agents        # Check agent data")
            print("  python check_db.py --recent        # Check recent activity")
            print("  python check_db.py --summary       # Quick summary")
            print("  python check_db.py --tender <ID>   # Check specific tender")
    else:
        main()