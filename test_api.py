"""
Test API Endpoints - Verify email settings API is working
Run this to test the API endpoints directly
"""
import asyncio
import requests
import json

BASE_URL = "http://localhost:8000"

def test_email_settings_api():
    """Test the email settings API endpoints"""
    
    print("=== Testing Email Settings API ===\n")
    
    # Test 1: Get current email settings
    print("1. Testing GET /api/v1/system/email-settings")
    try:
        response = requests.get(f"{BASE_URL}/api/v1/system/email-settings")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")
        else:
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   Connection Error: {e}")
    
    # Test 2: Add ESG email
    print("\n2. Testing POST /api/v1/system/email-settings/esg/add")
    try:
        test_email = "test-esg@example.com"
        payload = {"email": test_email}
        response = requests.post(f"{BASE_URL}/api/v1/system/email-settings/esg/add", json=payload)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json() if response.status_code == 200 else response.text}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 3: Add Credit Rating email
    print("\n3. Testing POST /api/v1/system/email-settings/credit_rating/add")
    try:
        test_email = "test-credit@example.com"
        payload = {"email": test_email}
        response = requests.post(f"{BASE_URL}/api/v1/system/email-settings/credit_rating/add", json=payload)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json() if response.status_code == 200 else response.text}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 4: Save complete email settings
    print("\n4. Testing POST /api/v1/system/email-settings")
    try:
        payload = {
            "esg_emails": ["esg1@company.com", "esg2@company.com"],
            "credit_rating_emails": ["credit1@company.com", "credit2@company.com"],
            "notification_preferences": {
                "send_for_new_tenders": True,
                "send_daily_summary": True,
                "send_urgent_notifications": True
            }
        }
        response = requests.post(f"{BASE_URL}/api/v1/system/email-settings", json=payload)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json() if response.status_code == 200 else response.text}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 5: Get settings again to verify
    print("\n5. Testing GET /api/v1/system/email-settings (after changes)")
    try:
        response = requests.get(f"{BASE_URL}/api/v1/system/email-settings")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")
        else:
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   Connection Error: {e}")

def test_server_health():
    """Test if server is running"""
    print("=== Testing Server Health ===\n")
    
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"Health check status: {response.status_code}")
        if response.status_code == 200:
            print(f"Response: {response.json()}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Server connection error: {e}")
        return False

if __name__ == "__main__":
    print("Email Settings API Test Tool\n")
    
    # First check if server is running
    if test_server_health():
        print("\n" + "="*50)
        test_email_settings_api()
    else:
        print("\n❌ Server is not running or not accessible")
        print("Please make sure your FastAPI server is running on http://localhost:8000")