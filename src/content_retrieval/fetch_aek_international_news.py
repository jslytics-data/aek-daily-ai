import logging
import os
import json
from datetime import datetime

from . import fetch_google_news_rss

log = logging.getLogger(__name__)

QUERY_TERM = "AEK"
DAYS_TO_LOOK_BACK = 0
TARGET_COUNTRY_CODES = [
    # Europe
    "AL", "AD", "AT", "BY", "BE", "BA", "BG", "HR", "CZ", "DK", 
    "EE", "FI", "FR", "DE", "HU", "IS", "IE", "IT", "LV", "LI", 
    "LT", "LU", "MT", "MD", "MC", "ME", "NL", "MK", "NO", "PL", "PT", 
    "RO", "SM", "RS", "SK", "SI", "ES", "SE", "CH", "UA", "GB",
    
    # Eurasia
    "RU", "TR",

    # North Africa
    "DZ", "EG", "LY", "MA", "TN",

    # Middle East & Gulf
    "BH", "IR", "IQ", "IL", "JO", "KW", "LB", "OM", "QA", "SA", "AE",

    # Other relevant football/transfer market countries
    "AR", "BR", "CO", "MX", "NG", "SN", "US", "UY", "AU"
]

def fetch_all_international_aek_news(days_to_look_back: int) -> list[dict]:
    log.info(f"Starting international news fetch for query '{QUERY_TERM}'.")
    
    all_collated_articles = []
    seen_article_links = set()

    for country_code in TARGET_COUNTRY_CODES:
        log.info(f"Fetching news for country: {country_code}")
        
        articles_from_country = fetch_google_news_rss.fetch_google_news_articles(
            query_term=QUERY_TERM,
            days_to_look_back=days_to_look_back,
            country_code=country_code
        )

        new_articles_found = 0
        for article in articles_from_country:
            article_link = article.get('rss_google_link')
            if article_link and article_link not in seen_article_links:
                all_collated_articles.append(article)
                seen_article_links.add(article_link)
                new_articles_found += 1
        
        log.info(f"Found {len(articles_from_country)} articles for {country_code}, added {new_articles_found} new unique articles.")

    log.info(f"Finished international fetch. Collated {len(all_collated_articles)} unique articles in total.")
    return all_collated_articles

def save_collated_articles_to_json(
    articles: list[dict],
    file_context_name: str,
    exports_dir: str = "exports"
) -> None:
    os.makedirs(exports_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_query = "".join(c for c in QUERY_TERM if c.isalnum()).lower()
    filename = f"{file_context_name}_{sanitized_query}_{timestamp_str}.json"
    filepath = os.path.join(exports_dir, filename)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        log.info(f"Saved {len(articles)} articles to: {filepath}")
    except IOError as e:
        log.error(f"Failed to write articles to file {filepath}. Error: {e}")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
    )
    
    log.info("--- Running fetch_aek_international_news.py test ---")
    
    collated_articles = fetch_all_international_aek_news(
        days_to_look_back=DAYS_TO_LOOK_BACK
    )

    if collated_articles:
        save_collated_articles_to_json(
            articles=collated_articles,
            file_context_name="aek_international_news_rss"
        )
        print(f"Successfully fetched and saved {len(collated_articles)} articles.")
    else:
        print("No articles found for the given test query across all countries.")

    log.info("--- fetch_aek_international_news.py test finished ---")