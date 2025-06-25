cd topical-ai
pip install -r requirements.txt
python -m src.content_retrieval.orchestrator
python -m src.content_retrieval.fetch_and_parse_dataforseo
python -m src.content_retrieval.fetch_google_news_rss
python -m src.content_retrieval.resolve_google_news_urls
python -m src.content_retrieval.extract_article_content
python -m src.content_retrieval.orchestrator
python -m src.content_retrieval.fetch_aek_international_news
python -m src.generate_base_digest
python -m src.format_adapters.generate_email_html
python -m src.format_adapters.generate_reddit_markdown
python -m src.distribution.send_sendgrid_email
python -m src.distribution.upload_to_gcs
python -m src.manager
python main.py