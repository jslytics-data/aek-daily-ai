import logging
import os
import json
import glob
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import trafilatura
from curl_cffi import requests as curl_requests

log = logging.getLogger(__name__)

MAX_CONCURRENT_REQUESTS = 2
REQUEST_TIMEOUT_SECONDS = 15
MIN_EXTRACTED_TEXT_LENGTH = 150
CURL_IMPERSONATE_VERSION = "chrome110"

def _fetch_html_with_curl(url: str, session: curl_requests.Session) -> tuple[str | None, str | None]:
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS, impersonate=CURL_IMPERSONATE_VERSION)
        response.raise_for_status()
        return response.text, None
    except Exception as e:
        error_type = type(e).__name__
        error_message = f"Fetch failed: {error_type}"
        log.warning(f"{error_message} for url {url}: {str(e)[:120]}")
        return None, error_message

def _extract_content_from_html(html_content: str, source_url: str) -> tuple[dict | None, str | None]:
    if not html_content:
        return None, "Extraction failed: HTML content was empty"
    try:
        extracted_json = trafilatura.extract(
            html_content,
            url=source_url,
            include_links=False,
            include_comments=False,
            output_format='json',
            with_metadata=True
        )
        if not extracted_json:
            return None, "Extraction failed: Trafilatura returned no data"

        content_dict = json.loads(extracted_json)
        return content_dict, None
    except Exception as e:
        error_type = type(e).__name__
        error_message = f"Extraction failed: {error_type}"
        log.warning(f"{error_message} for url {source_url}: {str(e)[:120]}")
        return None, error_message

def _process_single_article(article: dict, session: curl_requests.Session) -> dict:
    url = article.get('resolved_url')
    if not url:
        article['extraction_error'] = "No resolved_url to fetch"
        return article

    html, fetch_error = _fetch_html_with_curl(url, session)
    if fetch_error:
        article['extraction_error'] = fetch_error
        return article

    content, extract_error = _extract_content_from_html(html, url)
    if extract_error:
        article['extraction_error'] = extract_error
        return article

    article['extracted_title'] = content.get('title')
    article['extracted_text'] = content.get('text')
    article['extracted_date'] = content.get('date')
    article['extraction_error'] = None

    if not article['extracted_text'] or len(article['extracted_text']) < MIN_EXTRACTED_TEXT_LENGTH:
        article['extraction_error'] = "Extracted text is missing or too short"
        log.info(f"Marking article as failed due to short content: {url}")
    else:
        log.info(f"Successfully extracted content for: {url}")

    return article

def enrich_articles_with_extracted_content(articles: list[dict]) -> list[dict]:
    articles_to_process = [a for a in articles if a.get('resolved_url') and not a.get('resolution_error')]
    if not articles_to_process:
        log.info("No valid articles found for content extraction.")
        return articles

    log.info(f"Starting content extraction for {len(articles_to_process)} articles.")
    results = []
    session_headers = {
        "Referer": "https://www.google.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
    }

    with curl_requests.Session(headers=session_headers) as session:
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
            future_to_article = {executor.submit(_process_single_article, article, session): article for article in articles_to_process}
            for future in as_completed(future_to_article):
                try:
                    results.append(future.result())
                except Exception as e:
                    original_article = future_to_article[future]
                    log.error(f"Unhandled exception processing {original_article.get('resolved_url')}: {e}")
                    original_article['extraction_error'] = f"Unhandled Exception: {type(e).__name__}"
                    results.append(original_article)

    original_articles_by_url = {a['resolved_url']: a for a in articles}
    for res in results:
        original_articles_by_url[res['resolved_url']] = res

    return list(original_articles_by_url.values())

def save_articles_to_json_file(articles: list[dict], file_context_name: str, exports_dir: str = "exports") -> None:
    os.makedirs(exports_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{file_context_name}_{timestamp_str}.json"
    filepath = os.path.join(exports_dir, filename)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        log.info(f"Saved {len(articles)} articles to: {filepath}")
    except IOError as e:
        log.error(f"Failed to write articles to file {filepath}. Error: {e}")

def find_latest_input_file(search_dir: str) -> str | None:
    search_pattern = os.path.join(search_dir, "gnews_resolved_articles_*.json")
    try:
        list_of_files = glob.glob(search_pattern)
        return max(list_of_files, key=os.path.getctime) if list_of_files else None
    except Exception as e:
        log.error(f"Error finding input file in {search_dir}: {e}")
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    log.info("--- Running extract_article_content.py test ---")
    exports_directory = "exports"
    
    input_file_path = find_latest_input_file(exports_directory)

    if not input_file_path:
        log.error(f"No resolved articles file found in '{exports_directory}'.")
        log.error("Please run 'resolve_google_news_urls.py' first.")
    else:
        log.info(f"Using input file: {input_file_path}")
        with open(input_file_path, 'r', encoding='utf-8') as f:
            articles_from_resolver = json.load(f)

        fully_enriched_articles = enrich_articles_with_extracted_content(articles_from_resolver)

        if fully_enriched_articles:
            save_articles_to_json_file(
                articles=fully_enriched_articles,
                file_context_name="final_content_articles"
            )
            print("\n--- Test Results Summary ---")
            successful = sum(1 for a in fully_enriched_articles if a.get('extracted_text') and not a.get('extraction_error'))
            failed = len(fully_enriched_articles) - successful
            print(f"Successfully extracted content for: {successful} articles")
            print(f"Failed or skipped: {failed} articles")
        else:
            print("Processing returned no articles.")

    log.info("--- extract_article_content.py test finished ---")