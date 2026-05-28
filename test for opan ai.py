import os
import requests
from datetime import datetime, UTC
from dotenv import load_dotenv

# =========================================================
# LOAD ENV VARIABLES
# =========================================================

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")

if not API_KEY:
    raise ValueError("OPENAI_API_KEY not found in .env file")

# =========================================================
# CHECK RATE LIMITS
# =========================================================

def check_rate_limits():
    """
    Makes a tiny API request so OpenAI returns
    rate limit headers.
    """

    url = "https://api.openai.com/v1/responses"

    payload = {
        "model": "gpt-4.1-mini",
        "input": "Hello"
    }

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )

        print("\n==============================")
        print("OPENAI RATE LIMIT INFORMATION")
        print("==============================\n")

        print(f"Status Code: {response.status_code}\n")

        found = False

        for key, value in response.headers.items():
            if "ratelimit" in key.lower():
                found = True
                print(f"{key}: {value}")

        if not found:
            print("No rate limit headers were returned.\n")

        # Optional: print small response preview
        try:
            data = response.json()

            print("\n==============================")
            print("RESPONSE PREVIEW")
            print("==============================\n")

            if "output" in data:
                print("API request succeeded.")
            else:
                print(data)

        except Exception:
            print("Could not parse response JSON.")

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")


# =========================================================
# GET USAGE INFORMATION
# =========================================================

def get_usage_info():
    """
    Attempts to read usage information.
    Requires:
      api.usage.read permission
    """

    today = datetime.now(UTC).date()
    start_of_month = today.replace(day=1)

    url = (
        "https://api.openai.com/v1/organization/usage/completions"
        f"?start_time={start_of_month.isoformat()}"
        f"&end_time={today.isoformat()}"
    )

    try:
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            timeout=30
        )

        print("\n==============================")
        print("USAGE INFORMATION")
        print("==============================\n")

        if response.status_code == 200:
            data = response.json()
            print(data)

        else:
            print("Could not access usage API.\n")
            print(f"Status Code: {response.status_code}\n")

            try:
                error_data = response.json()
                print(error_data)

                if "Missing scopes" in str(error_data):
                    print("\nYour API key needs:")
                    print("api.usage.read permission")

            except Exception:
                print(response.text)

    except requests.exceptions.RequestException as e:
        print(f"Usage request failed: {e}")


# =========================================================
# ESTIMATE NEXT MONTHLY RESET
# =========================================================

def estimate_next_reset():
    """
    Estimates next monthly reset date.
    """

    now = datetime.now(UTC)

    if now.month == 12:
        next_reset = datetime(
            now.year + 1,
            1,
            1,
            tzinfo=UTC
        )
    else:
        next_reset = datetime(
            now.year,
            now.month + 1,
            1,
            tzinfo=UTC
        )

    remaining = next_reset - now

    days = remaining.days
    hours = remaining.seconds // 3600
    minutes = (remaining.seconds % 3600) // 60

    print("\n==============================")
    print("ESTIMATED MONTHLY RESET")
    print("==============================\n")

    print("Current UTC Time:")
    print(now.strftime("%Y-%m-%d %H:%M:%S UTC"))

    print("\nEstimated Reset:")
    print(next_reset.strftime("%Y-%m-%d %H:%M:%S UTC"))

    print("\nTime Remaining:")
    print(f"{days} days, {hours} hours, {minutes} minutes")


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    print("\nStarting OpenAI account inspection...\n")

    check_rate_limits()

    get_usage_info()

    estimate_next_reset()

    print("\nDone.\n")