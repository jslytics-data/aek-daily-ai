import os
import logging

if "K_SERVICE" in os.environ:
    import google.cloud.logging
    google.cloud.logging.Client().setup_logging()
else:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
    )

from flask import Flask, request, jsonify
from dotenv import load_dotenv
from functools import wraps
from src import manager

load_dotenv()
app = Flask(__name__)
log = logging.getLogger(__name__)

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = os.getenv("INTERNAL_API_KEY")
        if not api_key:
            log.error("CRITICAL: INTERNAL_API_KEY is not configured on the server.")
            return jsonify({"status": "error", "message": "Service is not configured."}), 500
        
        provided_key = request.headers.get("X-API-Key")
        if not provided_key or provided_key != api_key:
            log.warning(f"Unauthorized access attempt from IP: {request.remote_addr}")
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
        return f(*args, **kwargs)
    return decorated_function

@app.route("/run-digest", methods=["POST"])
@require_api_key
def run_digest_endpoint():
    request_data = request.get_json()
    if not request_data:
        return jsonify({"status": "error", "message": "Invalid JSON payload."}), 400

    query_term = request_data.get("query_term")
    language_code = request_data.get("language_code")
    location_code = request_data.get("location_code")

    if not all([query_term, language_code, location_code]):
        msg = "Missing one or more required fields: query_term, language_code, location_code."
        return jsonify({"status": "error", "message": msg}), 400

    days_to_look_back = request_data.get("days_to_look_back", 1)
    distribution_options = request_data.get("distribution", {})
    
    upload_gcs = distribution_options.get("gcs", {}).get("enabled", False)
    send_email = distribution_options.get("email", {}).get("enabled", False)
    post_reddit = distribution_options.get("reddit", {}).get("enabled", False)
    
    recipient_emails = distribution_options.get("email", {}).get("recipients")
    reddit_subreddit = distribution_options.get("reddit", {}).get("subreddit")
    reddit_flair_id = distribution_options.get("reddit", {}).get("flair_id")

    log.info(f"Received valid request to run digest for query: '{query_term}'")
    
    try:
        success = manager.run_full_digest_pipeline(
            query_term=query_term,
            days_to_look_back=days_to_look_back,
            language_code=language_code,
            location_code=location_code,
            save_intermediate_files=False, # Set to False for production runs
            upload_to_gcs_enabled=upload_gcs,
            send_email_enabled=send_email,
            post_to_reddit_enabled=post_reddit,
            recipient_emails_str=recipient_emails,
            reddit_subreddit=reddit_subreddit,
            reddit_flair_id=reddit_flair_id
        )

        if success:
            log.info(f"Pipeline completed successfully for query: '{query_term}'")
            return jsonify({"status": "success", "message": "Digest pipeline completed."}), 200
        else:
            log.error(f"Pipeline failed for query: '{query_term}'")
            return jsonify({"status": "error", "message": "Digest pipeline failed during execution."}), 500

    except Exception as e:
        log.critical(f"An unhandled exception occurred in the manager: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "An internal server error occurred."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)