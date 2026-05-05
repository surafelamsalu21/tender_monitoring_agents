"""
Test Email API Endpoints (screening / opportunity_emails model).
Run this script to test the email settings API endpoints.
"""
import requests
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000/api/v1/system"
SCREENING_CATEGORY = "screening_opportunities"


def test_get_email_settings():
    """Test GET /email-settings endpoint"""
    try:
        response = requests.get(f"{BASE_URL}/email-settings")
        logger.info(f"GET /email-settings - Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            logger.info(f"Response: {json.dumps(data, indent=2)}")
            return data
        logger.error(f"Error: {response.text}")
        return None
    except Exception as e:
        logger.error(f"Exception: {e}")
        return None


def test_save_email_settings(opportunity_emails: list):
    """Test POST /email-settings endpoint"""
    try:
        payload = {
            "opportunity_emails": opportunity_emails,
            "notification_preferences": {
                "send_for_new_tenders": True,
                "send_daily_summary": True,
                "send_urgent_notifications": True,
            },
        }

        response = requests.post(
            f"{BASE_URL}/email-settings",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        logger.info(f"POST /email-settings - Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            logger.info(f"Response: {json.dumps(data, indent=2)}")
            return data
        logger.error(f"Error: {response.text}")
        return None
    except Exception as e:
        logger.error(f"Exception: {e}")
        return None


def test_add_email(category: str, email: str):
    """Test POST /email-settings/{category}/add endpoint"""
    try:
        payload = {"email": email}

        response = requests.post(
            f"{BASE_URL}/email-settings/{category}/add",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        logger.info(f"POST /email-settings/{category}/add - Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            logger.info(f"Response: {json.dumps(data, indent=2)}")
            return data
        logger.error(f"Error: {response.text}")
        return None
    except Exception as e:
        logger.error(f"Exception: {e}")
        return None


def test_remove_email(category: str, email: str):
    """Test DELETE /email-settings/{category}/{email} endpoint"""
    try:
        response = requests.delete(
            f"{BASE_URL}/email-settings/{category}/{email}"
        )

        logger.info(
            f"DELETE /email-settings/{category}/{email} - Status: {response.status_code}"
        )

        if response.status_code == 200:
            data = response.json()
            logger.info(f"Response: {json.dumps(data, indent=2)}")
            return data
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

    logger.info("\n1. Getting initial email settings...")
    initial_settings = test_get_email_settings()

    if initial_settings:
        logger.info("✅ GET email-settings working")
    else:
        logger.error("❌ GET email-settings failed")
        return False

    logger.info(
        f"\n2. Testing add email endpoint - adding {test_email_1} to {SCREENING_CATEGORY}..."
    )
    add_result = test_add_email(SCREENING_CATEGORY, test_email_1)

    if add_result and add_result.get("success"):
        logger.info("✅ Add email endpoint working")
    else:
        logger.error("❌ Add email endpoint failed")

    logger.info("\n3. Verifying email was added...")
    after_add_settings = test_get_email_settings()

    opp_after_add = (
        after_add_settings.get("settings", {}).get("opportunity_emails", [])
        if after_add_settings
        else []
    )
    if after_add_settings and test_email_1 in opp_after_add:
        logger.info("✅ Email successfully added and verified")
    else:
        logger.error("❌ Email not found after adding")

    logger.info(f"\n4. Testing save settings endpoint - adding {test_email_2}...")
    current = list(opp_after_add)
    if test_email_2 not in current:
        current.append(test_email_2)

    save_result = test_save_email_settings(current)

    if save_result and save_result.get("success"):
        logger.info("✅ Save settings endpoint working")
    else:
        logger.error("❌ Save settings endpoint failed")

    logger.info("\n5. Verifying multiple emails...")
    after_save_settings = test_get_email_settings()

    if after_save_settings:
        opp = after_save_settings["settings"]["opportunity_emails"]
        if test_email_1 in opp and test_email_2 in opp:
            logger.info("✅ Both emails successfully saved and verified")
        else:
            logger.error(f"❌ Not all emails found. Current list: {opp}")

    logger.info(f"\n6. Testing remove email endpoint - removing {test_email_1}...")
    remove_result = test_remove_email(SCREENING_CATEGORY, test_email_1)

    if remove_result and remove_result.get("success"):
        logger.info("✅ Remove email endpoint working")
    else:
        logger.error("❌ Remove email endpoint failed")

    logger.info("\n7. Verifying email was removed...")
    after_remove_settings = test_get_email_settings()

    if after_remove_settings:
        opp = after_remove_settings["settings"]["opportunity_emails"]
        if test_email_1 not in opp and test_email_2 in opp:
            logger.info("✅ Email successfully removed and verified")
        else:
            logger.error(f"❌ Email removal verification failed. Current list: {opp}")

    logger.info(f"\n8. Cleaning up - removing {test_email_2}...")
    cleanup_result = test_remove_email(SCREENING_CATEGORY, test_email_2)

    if cleanup_result and cleanup_result.get("success"):
        logger.info("✅ Cleanup successful")
    else:
        logger.error("❌ Cleanup failed")

    logger.info("\n9. Final verification...")
    final_settings = test_get_email_settings()

    if final_settings:
        opp = final_settings["settings"]["opportunity_emails"]
        if test_email_1 not in opp and test_email_2 not in opp:
            logger.info("✅ All test emails successfully removed")
        else:
            logger.warning(f"⚠️ Some test emails still present: {opp}")

    logger.info("\n" + "=" * 60)
    logger.info("EMAIL API TEST COMPLETED")
    logger.info("=" * 60)

    return True


if __name__ == "__main__":
    print("Testing Email API Endpoints...")
    print("Make sure your FastAPI server is running on http://localhost:8000")
    print("And that you've run the database initialization script first.\n")

    try:
        run_comprehensive_test()
        print("\n✅ All tests completed!")
        print("\nIf all tests passed, your email API is working correctly.")
        print("You can now use the frontend Settings tab to manage emails.")

    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        print(
            "Make sure your FastAPI server is running and the database is initialized."
        )
