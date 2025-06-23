import logging
import os
import glob
import json
from datetime import datetime

import requests
from dotenv import load_dotenv

log = logging.getLogger(__name__)

def _refresh_access_token() -> tuple[str | None, str | None]:
    log.info("Attempting to refresh Reddit access token.")
    
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    refresh_token = os.getenv("REDDIT_REFRESH_TOKEN")
    user_agent = os.getenv("REDDIT_USER_AGENT")

    if not all([client_id, client_secret, refresh_token, user_agent]):
        log.error("One or more required Reddit environment variables are missing.")
        return None, None

    token_endpoint = "https://www.reddit.com/api/v1/access_token"
    headers = {"User-Agent": user_agent}
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    auth = (client_id, client_secret)

    try:
        response = requests.post(url=token_endpoint, auth=auth, headers=headers, data=data, timeout=15)
        response.raise_for_status()
        
        token_data = response.json()
        new_access_token = token_data.get("access_token")
        
        if not new_access_token:
            log.error("Token refresh successful, but no access_token in response.")
            return None, None

        log.info("Successfully refreshed Reddit access token.")
        new_refresh_token = token_data.get("refresh_token")
        return new_access_token, new_refresh_token

    except requests.exceptions.HTTPError as e:
        log.error(f"HTTP error during token refresh: {e.response.status_code}")
        if e.response.status_code == 400:
            log.error("Hint: Status 400 (Bad Request) often means the refresh token is invalid or has been revoked.")
        log.debug(f"Reddit error response: {e.response.text}")
        return None, None
    except Exception as e:
        log.error(f"An unexpected error occurred during token refresh: {e}", exc_info=True)
        return None, None

def _save_submission_response(response_data: dict, title: str, exports_dir: str) -> None:
    os.makedirs(exports_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in title if c.isalnum())[:30]
    filename = f"reddit_submission_{safe_title}_{timestamp}.json"
    filepath = os.path.join(exports_dir, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(response_data, f, indent=2, ensure_ascii=False)
        log.info(f"Reddit submission response saved to: {filepath}")
    except IOError as e:
        log.error(f"Failed to save Reddit submission response: {e}")

def post_content_to_reddit(
    subreddit: str,
    title: str,
    markdown_body: str,
    flair_id: str | None = None
) -> tuple[bool, str | None]:
    
    log.info(f"Attempting to post to r/{subreddit} with title: '{title[:50]}...'")
    user_agent = os.getenv("REDDIT_USER_AGENT")
    if not user_agent:
        log.critical("REDDIT_USER_AGENT environment variable not set.")
        return False, None

    access_token, _ = _refresh_access_token()
    if not access_token:
        log.error("Failed to get a valid access token. Cannot submit post.")
        return False, None

    headers = {"Authorization": f"Bearer {access_token}", "User-Agent": user_agent}
    data = {
        "sr": subreddit,
        "title": title,
        "kind": "self",
        "text": markdown_body,
        "api_type": "json"
    }
    if flair_id:
        data["flair_id"] = flair_id
        log.info(f"Using flair ID: {flair_id}")

    try:
        response = requests.post("https://oauth.reddit.com/api/submit", headers=headers, data=data, timeout=30)
        response.raise_for_status()
        
        response_json = response.json()
        if response_json.get("json", {}).get("errors"):
            errors = response_json["json"]["errors"]
            log.error(f"Reddit API returned errors: {errors}")
            return False, None

        post_url = response_json.get("json", {}).get("data", {}).get("url")
        if not post_url:
            log.error(f"Submission seemed successful, but no post URL found in response.")
            log.debug(f"Full Reddit Response: {response_json}")
            return False, None
            
        log.info(f"Post successfully submitted. URL: {post_url}")
        _save_submission_response(response_json, title, "exports")
        return True, post_url

    except requests.exceptions.HTTPError as e:
        log.error(f"HTTP error posting to Reddit: {e.response.status_code}")
        log.debug(f"Reddit Error Response Body: {e.response.text}")
        return False, None
    except Exception as e:
        log.error(f"An unexpected error occurred while posting to Reddit: {e}", exc_info=True)
        return False, None

def _find_latest_file_by_pattern(directory: str, pattern: str) -> str | None:
    try:
        search_path = os.path.join(directory, pattern)
        list_of_files = glob.glob(search_path)
        return max(list_of_files, key=os.path.getctime) if list_of_files else None
    except Exception as e:
        log.error(f"Error finding latest file with pattern '{pattern}': {e}")
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    load_dotenv()
    log.info("--- Running post_to_reddit.py test ---")
    
    test_subreddit = "testingground4bots"
    test_flair_id = None # Optional: Set to a specific flair UUID if needed
    
    markdown_path = _find_latest_file_by_pattern("exports", "reddit_adapted_markdown_*.md")
    if not markdown_path:
        log.error("No Reddit markdown file found in 'exports/'.")
        log.error("Please run 'format_adapters.reddit_adapter' first.")
    else:
        log.info(f"Using markdown file for test post: {markdown_path}")
        try:
            with open(markdown_path, 'r', encoding='utf-8') as f:
                markdown_content = f.read()

            test_title = f"AI Digest Test Post - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            success, url = post_content_to_reddit(
                subreddit=test_subreddit,
                title=test_title,
                markdown_body=markdown_content,
                flair_id=test_flair_id
            )
            
            if success:
                print("\n--- Test Result: Success ---")
                print(f"Post submitted to r/{test_subreddit}: {url}")
            else:
                print("\n--- Test Result: Failure ---")
                print("Could not post to Reddit. Check logs for details.")

        except Exception as e:
            log.error(f"Error during CLI test execution: {e}", exc_info=True)
    
    log.info("--- post_to_reddit.py test finished ---")