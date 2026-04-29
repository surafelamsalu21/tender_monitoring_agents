"""
Test Email API Endpoints
Run this script to test the email settings API endpoints
"""
import requests
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000/api/v1/system"

def test_get_email_settings():
    """Test GET /email-settings endpoint"""
    try:
        response = requests.get(f"{BASE_URL}/email-settings")
        logger.info(f"GET /email-settings - Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Response: {json.dumps(data, indent=2)}")
            return data
        else:
            logger.error(f"Error: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Exception: {e}")
        return None

def test_save_email_settings(esg_emails, credit_emails):
    """Test POST /email-settings endpoint"""
    try:
        payload = {
            "esg_emails": esg_emails,
            "credit_rating_emails": credit_emails,
            "notification_preferences": {
                "send_for_new_tenders": True,
                "send_daily_summary": True,
                "send_urgent_notifications": True
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/email-settings",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        logger.info(f"POST /email-settings - Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Response: {json.dumps(data, indent=2)}")
            return data
        else:
            logger.error(f"Error: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Exception: {e}")
        return None

def test_add_email(category, email):
    """Test POST /email-settings/{category}/add endpoint"""
    try:
        payload = {"email": email}
        
        response = requests.post(
            f"{BASE_URL}/email-settings/{category}/add",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        logger.info(f"POST /email-settings/{category}/add - Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Response: {json.dumps(data, indent=2)}")
            return data
        else:
            logger.error(f"Error: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Exception: {e}")
        return None

def test_remove_email(category, email):
    """Test DELETE /email-settings/{category}/{email} endpoint"""
    try:
        response = requests.delete(f"{BASE_URL}/email-settings/{category}/{email}")
        
        logger.info(f"DELETE /email-settings/{category}/{email} - Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Response: {json.dumps(data, indent=2)}")
            return data
        else:
            logger.error(f"Error: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Exception: {e}")
        return None

def run_comprehensive_test():
    """Run comprehensive test of all email API endpoints"""
    logger.info("=" * 60)
    logger.info("STARTING COMPREHENSIVE EMAIL API TEST")
    logger.info("=" * 60)
    
    test_email_1 = "test1@example.com"
    test_email_2 = "test2@example.com"
    
    # Step 1: Get initial settings
    logger.info("\n1. Getting initial email settings...")
    initial_settings = test_get_email_settings()
    
    if initial_settings:
        logger.info("✅ GET email-settings working")
    else:
        logger.error("❌ GET email-settings failed")
        return False
    
    # Step 2: Test adding emails via the add endpoint
    logger.info(f"\n2. Testing add email endpoint - adding {test_email_1} to ESG...")
    add_result = test_add_email("esg", test_email_1)
    
    if add_result and add_result.get("success"):
        logger.info("✅ Add email endpoint working")
    else:
        logger.error("❌ Add email endpoint failed")
    
    # Step 3: Verify the email was added
    logger.info("\n3. Verifying email was added...")
    after_add_settings = test_get_email_settings()
    
    if after_add_settings and test_email_1 in after_add_settings['settings']['esg_emails']:
        logger.info("✅ Email successfully added and verified")
    else:
        logger.error("❌ Email not found after adding")
    
    # Step 4: Test adding multiple emails via save settings endpoint
    logger.info(f"\n4. Testing save settings endpoint - adding {test_email_2}...")
    current_esg_emails = after_add_settings['settings']['esg_emails'] if after_add_settings else []
    current_credit_emails = after_add_settings['settings']['credit_rating_emails'] if after_add_settings else []
    
    # Add test_email_2 to ESG emails
    new_esg_emails = current_esg_emails + [test_email_2] if test_email_2 not in current_esg_emails else current_esg_emails
    
    save_result = test_save_email_settings(new_esg_emails, current_credit_emails)
    
    if save_result and save_result.get("success"):
        logger.info("✅ Save settings endpoint working")
    else:
        logger.error("❌ Save settings endpoint failed")
    
    # Step 5: Verify both emails are present
    logger.info("\n5. Verifying multiple emails...")
    after_save_settings = test_get_email_settings()
    
    if after_save_settings:
        esg_emails = after_save_settings['settings']['esg_emails']
        if test_email_1 in esg_emails and test_email_2 in esg_emails:
            logger.info("✅ Both emails successfully saved and verified")
        else:
            logger.error(f"❌ Not all emails found. Current ESG emails: {esg_emails}")
    
    # Step 6: Test removing an email
    logger.info(f"\n6. Testing remove email endpoint - removing {test_email_1}...")
    remove_result = test_remove_email("esg", test_email_1)
    
    if remove_result and remove_result.get("success"):
        logger.info("✅ Remove email endpoint working")
    else:
        logger.error("❌ Remove email endpoint failed")
    
    # Step 7: Verify the email was removed
    logger.info("\n7. Verifying email was removed...")
    after_remove_settings = test_get_email_settings()
    
    if after_remove_settings:
        esg_emails = after_remove_settings['settings']['esg_emails']
        if test_email_1 not in esg_emails and test_email_2 in esg_emails:
            logger.info("✅ Email successfully removed and verified")
        else:
            logger.error(f"❌ Email removal verification failed. Current ESG emails: {esg_emails}")
    
    # Step 8: Clean up - remove remaining test email
    logger.info(f"\n8. Cleaning up - removing {test_email_2}...")
    cleanup_result = test_remove_email("esg", test_email_2)
    
    if cleanup_result and cleanup_result.get("success"):
        logger.info("✅ Cleanup successful")
    else:
        logger.error("❌ Cleanup failed")
    
    # Step 9: Final verification
    logger.info("\n9. Final verification...")
    final_settings = test_get_email_settings()
    
    if final_settings:
        esg_emails = final_settings['settings']['esg_emails']
        if test_email_1 not in esg_emails and test_email_2 not in esg_emails:
            logger.info("✅ All test emails successfully removed")
        else:
            logger.warning(f"⚠️ Some test emails still present: {esg_emails}")
    
    logger.info("\n" + "=" * 60)
    logger.info("EMAIL API TEST COMPLETED")
    logger.info("=" * 60)
    
    return True

def test_credit_rating_emails():
    """Test credit rating email functionality"""
    logger.info("\n" + "=" * 60)
    logger.info("TESTING CREDIT RATING EMAIL FUNCTIONALITY")
    logger.info("=" * 60)
    
    test_email = "credit.test@example.com"
    
    # Add email to credit rating category
    logger.info(f"Adding {test_email} to credit_rating category...")
    add_result = test_add_email("credit_rating", test_email)
    
    if add_result and add_result.get("success"):
        logger.info("✅ Credit rating email add successful")
        
        # Verify it was added
        settings = test_get_email_settings()
        if settings and test_email in settings['settings']['credit_rating_emails']:
            logger.info("✅ Credit rating email verified")
            
            # Remove it
            logger.info(f"Removing {test_email} from credit_rating category...")
            remove_result = test_remove_email("credit_rating", test_email)
            
            if remove_result and remove_result.get("success"):
                logger.info("✅ Credit rating email removal successful")
            else:
                logger.error("❌ Credit rating email removal failed")
        else:
            logger.error("❌ Credit rating email not found after adding")
    else:
        logger.error("❌ Credit rating email add failed")

if __name__ == "__main__":
    print("Testing Email API Endpoints...")
    print("Make sure your FastAPI server is running on http://localhost:8000")
    print("And that you've run the database initialization script first.\n")
    
    try:
        # Test basic functionality
        run_comprehensive_test()
        
        # Test credit rating emails
        test_credit_rating_emails()
        
        print("\n✅ All tests completed!")
        print("\nIf all tests passed, your email API is working correctly.")
        print("You can now use the frontend Settings tab to manage emails.")
        
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        print("Make sure your FastAPI server is running and the database is initialized.")