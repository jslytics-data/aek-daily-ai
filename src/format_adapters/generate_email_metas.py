import logging
import os
import json
import glob
from datetime import datetime

import litellm
from dotenv import load_dotenv

litellm.set_verbose = False
log = logging.getLogger(__name__)

TEMPERATURE = 1
EMAIL_METAS_PROMPT_TEMPLATE = """
You are an expert email marketer and copywriter with a style similar to Morning Brew. Your goal is to maximize open rates.
You will be given the full HTML content of a newsletter.

Your task is to analyze the content and generate:
1.  **Subject Line:** Must be concise, powerful, and capture the most important news within the digest. It must be in the same language as the newsletter content. You can add a single emoji if you think its a good fit.
2.  **Preview Text:** A short, enticing sentence that appears after the subject line in an email client. It must complement the subject without repeating it, giving another reason to open the email. Keep it under 150 characters.

The name of the newsletter will be included in the From Name, so no need to include it. The date will also be included in the email service provider timeline.

Your output MUST be a valid JSON object with exactly two keys: "subject_line" and "preview_text". Do not include any other text, explanations, or markdown formatting around the JSON.
"""

def generate_email_metadata_from_html(base_html_content: str) -> dict[str, str] | None:
    log.info("Starting email metadata generation process.")

    if not os.getenv("GEMINI_API_KEY"):
        log.error("GEMINI_API_KEY not found in environment for LiteLLM.")
        return None
        
    model_string = os.getenv("LITELLM_MODEL_STRING")
    if not model_string:
        log.error("LITELLM_MODEL_STRING not found in environment.")
        return None

    if not base_html_content:
        log.error("Base HTML content must be provided.")
        return None

    full_prompt_for_llm = (
        f"{EMAIL_METAS_PROMPT_TEMPLATE}\n\n"
        f"--- Base HTML Newsletter Content ---\n"
        f"{base_html_content}"
    )

    messages = [{"role": "user", "content": full_prompt_for_llm}]
    
    completion_kwargs = {
        "model": model_string, 
        "messages": messages, 
        "temperature": TEMPERATURE,
        "response_format": {"type": "json_object"}
    }

    try:
        log.info(f"Requesting email metadata from LiteLLM model: {model_string}")
        response = litellm.completion(**completion_kwargs)
        
        if not (response and response.choices and response.choices[0].message and response.choices[0].message.content):
            log.warning("No valid content in LiteLLM response for email metadata.")
            return None

        content_str = response.choices[0].message.content
        data = json.loads(content_str)
        
        subject = data.get("subject_line")
        preview = data.get("preview_text")
        
        if not subject or not preview:
            log.error(f"LLM JSON response missing 'subject_line' or 'preview_text'. Response: {data}")
            return None

        log.info(f"Successfully generated email metadata. Subject: '{subject}'")
        return {"subject_line": subject, "preview_text": preview}

    except json.JSONDecodeError:
        log.error(f"Failed to decode JSON from LLM response. Raw: {response.choices[0].message.content[:300]}...")
        return None
    except Exception as e:
        log.error(f"LiteLLM error during email metadata generation: {e}", exc_info=True)
        return None

def _save_metas_to_json_file(metas: dict, query_term: str, exports_dir: str = "exports") -> None:
    os.makedirs(exports_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_query = "".join(c for c in query_term if c.isalnum()).lower()
    filename = f"email_metas_{sanitized_query}_{timestamp_str}.json"
    filepath = os.path.join(exports_dir, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(metas, f, indent=2, ensure_ascii=False)
        log.info(f"Saved email metadata to: {filepath}")
    except IOError as e:
        log.error(f"Failed to write metadata to file {filepath}. Error: {e}")

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

    log.info("--- Running generate_email_metas.py test ---")

    if not os.getenv("GEMINI_API_KEY") or not os.getenv("LITELLM_MODEL_STRING"):
        log.critical("GEMINI_API_KEY or LITELLM_MODEL_STRING not in .env. Test cannot run.")
    else:
        exports_dir = "exports"
        base_html_path = _find_latest_file_by_pattern(exports_dir, "base_digest_html_*.html")

        if not base_html_path:
            log.error("Could not find latest base HTML file in 'exports/'.")
            log.error("Please run 'generate_base_digest.py' first.")
        else:
            log.info(f"Using base HTML file for test: {base_html_path}")
            try:
                with open(base_html_path, 'r', encoding='utf-8') as f:
                    base_html = f.read()
                
                filename_parts = os.path.basename(base_html_path).split('_')
                query_term = "testquery"
                if len(filename_parts) > 3:
                    query_term = filename_parts[3]
                
                log.info(f"Extracted query term for test: {query_term}")

                email_metas = generate_email_metadata_from_html(base_html)
                
                if email_metas:
                    log.info("Email metadata generated successfully for test.")
                    print("\n--- Generated Email Metadata ---")
                    print(json.dumps(email_metas, indent=2, ensure_ascii=False))
                    _save_metas_to_json_file(email_metas, query_term)
                else:
                    log.error("Failed to generate email metadata during test.")
                    print("\n--- Email Metadata Generation FAILED ---")

            except Exception as e:
                log.error(f"Error during CLI test execution: {e}", exc_info=True)

    log.info("--- generate_email_metas.py test finished ---")