import logging
import os
import json
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

log = logging.getLogger(__name__)

DATAFORSEO_API_URL = "https://api.dataforseo.com/v3/serp/google/news/live/advanced"

def _filter_articles_by_recency(articles: list[dict], days_to_look_back: int) -> list[dict]:
    if days_to_look_back < 0:
        return articles

    filtered_list = []
    start_date_utc = (datetime.now(timezone.utc) - timedelta(days=days_to_look_back)).date()
    log.info(f"Filtering articles from {start_date_utc.isoformat()} to now.")

    for article in articles:
        pub_date_str = article.get("publication_date")
        if not pub_date_str:
            log.warning(f"Skipping article with null publication_date: {article.get('title', 'N/A')[:50]}...")
            continue
        try:
            # Assumes timestamp is in "YYYY-MM-DD HH:MM:SS +00:00" format
            article_pub_date = datetime.fromisoformat(pub_date_str.replace(" +00:00", "+00:00")).date()
            if article_pub_date >= start_date_utc:
                filtered_list.append(article)
        except (ValueError, TypeError) as e:
            log.warning(f"Could not parse publication_date '{pub_date_str}': {e}. Skipping article.")
            continue
    
    log.info(f"Filtered {len(articles)} down to {len(filtered_list)} articles.")
    return filtered_list

def _parse_dataforseo_response(response: dict) -> list[dict]:
    extracted_articles = []
    if not response:
        log.warning("Parser received an empty response.")
        return []

    try:
        tasks = response.get("tasks", [])
        if not tasks or tasks[0].get("status_code") != 20000:
            status_msg = tasks[0].get("status_message", "Unknown error") if tasks else "No tasks in response"
            log.error(f"DataForSEO task failed: {status_msg}")
            return []
        
        results = tasks[0].get("result", [])
        if not results:
            log.info("DataForSEO task succeeded but returned no results.")
            return []

        for item in results[0].get("items", []):
            item_type = item.get("type")
            
            if item_type == "news_search":
                if item.get("url") and item.get("title"):
                    extracted_articles.append({
                        "title": item.get("title"),
                        "resolved_url": item.get("url"),
                        "publication_date": item.get("timestamp"),
                        "source_domain": item.get("domain")
                    })
            elif item_type == "top_stories":
                for sub_item in item.get("items", []):
                    if sub_item.get("url") and sub_item.get("title"):
                         extracted_articles.append({
                            "title": sub_item.get("title"),
                            "resolved_url": sub_item.get("url"),
                            "publication_date": sub_item.get("timestamp"),
                            "source_domain": sub_item.get("domain")
                        })
    except (KeyError, IndexError, TypeError) as e:
        log.error(f"Error parsing DataForSEO response structure: {e}", exc_info=True)
        return []

    log.info(f"Parsed {len(extracted_articles)} articles from DataForSEO response.")
    return extracted_articles

def fetch_and_parse_dataforseo_news(query_term: str, language_code: str, location_code: int, days_to_look_back: int) -> list[dict]:
    log.info(f"Starting news fetch from DataForSEO for query: '{query_term}'")
    
    login = os.getenv("DATAFORSEO_LOGIN")
    password = os.getenv("DATAFORSEO_PASSWORD")
    if not login or not password:
        log.error("DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD must be set in .env file.")
        return []

    post_payload = [{"language_code": language_code, "location_code": location_code, "keyword": query_term}]

    try:
        log.info(f"Posting to DataForSEO with query '{query_term}' for location '{location_code}'")
        response = requests.post(
            DATAFORSEO_API_URL,
            headers={"Content-Type": "application/json"},
            json=post_payload,
            auth=(login, password),
            timeout=30
        )
        response.raise_for_status()
        
        response_data = response.json()
        if response_data.get("status_code") != 20000:
            log.error(f"DataForSEO API Error: {response_data.get('status_message')}")
            return []
        
        parsed_articles = _parse_dataforseo_response(response_data)
        return _filter_articles_by_recency(parsed_articles, days_to_look_back)

    except requests.exceptions.HTTPError as e:
        log.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
        return []
    except Exception as e:
        log.error(f"An exception occurred during DataForSEO API call: {e}", exc_info=True)
        return []

def save_articles_to_json_file(articles: list[dict], query_term: str, file_context_name: str, exports_dir: str = "exports") -> None:
    os.makedirs(exports_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_query = "".join(c for c in query_term if c.isalnum()).lower()
    filename = f"{file_context_name}_{sanitized_query}_{timestamp_str}.json"
    filepath = os.path.join(exports_dir, filename)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        log.info(f"Saved {len(articles)} articles to: {filepath}")
    except IOError as e:
        log.error(f"Failed to write articles to file {filepath}. Error: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    load_dotenv()

    log.info("--- Running fetch_and_parse_dataforseo.py test ---")
    
    test_query = "ΑΕΚ"
    test_lang = "el"
    test_loc_code = 2300 # Greece
    test_days_back = 1

    if not (os.getenv("DATAFORSEO_LOGIN") and os.getenv("DATAFORSEO_PASSWORD")):
        log.critical("DATAFORSEO credentials not found in .env. Test cannot run.")
    else:
        articles = fetch_and_parse_dataforseo_news(
            query_term=test_query,
            language_code=test_lang,
            location_code=test_loc_code,
            days_to_look_back=test_days_back
        )

        if articles:
            log.info(f"Test successful. Fetched and parsed {len(articles)} articles.")
            save_articles_to_json_file(articles, test_query, "dataforseo_parsed_articles")
            print("\n--- Test Result: Success ---")
            print(f"Fetched, filtered, and saved {len(articles)} parsed articles.")
            print("Sample:", json.dumps(articles[0], indent=2, ensure_ascii=False))
        else:
            log.error("Test failed. No articles were fetched or parsed.")
            print("\n--- Test Result: Failure ---")
            print("Could not fetch articles. Check logs for details.")

    log.info("--- fetch_and_parse_dataforseo.py test finished ---")