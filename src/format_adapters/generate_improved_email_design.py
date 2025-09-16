import logging
import os
import glob
import re
from datetime import datetime

import litellm
from dotenv import load_dotenv

litellm.set_verbose = False
log = logging.getLogger(__name__)

TEMPERATURE = 1.0
MAX_TOKENS = 32000
MODEL_NAME = "anthropic/claude-opus-4-1-20250805"

IMPROVEMENT_PROMPT_TEMPLATE = """
You are an expert email designer.
Your task is to improve the provided email HTML. 
The final output should be a mobile-optimised email HTML Newsletter, with a simple, clean, and beautiful design.
Do not change the text content, only improve the HTML structure and CSS styling.
Important: On mobile devices, minimize side margins so that text has room, otherwise it looks squashed. 
Do not use dark backgrounds.
Your final output MUST be only the new, complete HTML code and nothing else.
"""

def _clean_llm_html_output(raw_html_text: str) -> str | None:
    if not raw_html_text or not isinstance(raw_html_text, str):
        return None
    
    cleaned_text = raw_html_text.strip()
    
    if cleaned_text.startswith("```html"):
        cleaned_text = cleaned_text[len("```html"):].strip()
    if cleaned_text.endswith("```"):
        cleaned_text = cleaned_text[:-len("```")].strip()

    start_match = re.search(r"<!DOCTYPE\s+html|<html", cleaned_text, re.IGNORECASE)
    if not start_match:
        log.warning("Could not find standard HTML start in LLM output.")
        return cleaned_text if cleaned_text.startswith("<") and cleaned_text.endswith(">") else None
    
    start_index = start_match.start()
    last_end_tag_index = cleaned_text.rfind("</html>")
    
    if last_end_tag_index == -1:
        log.warning("Could not find standard HTML end tag in LLM output.")
        return cleaned_text[start_index:].strip()
        
    return cleaned_text[start_index : last_end_tag_index + len("</html>")].strip()

def improve_html_digest_design(base_html_content: str) -> str | None:
    log.info("Starting HTML design improvement process.")
    
    if not os.getenv("ANTHROPIC_API_KEY"):
        log.error("ANTHROPIC_API_KEY not found in environment.")
        return None

    if not base_html_content:
        log.error("Base HTML content for improvement must be provided.")
        return None

    full_prompt_for_llm = f"{IMPROVEMENT_PROMPT_TEMPLATE}\n\n```html\n{base_html_content}\n```"
    messages = [{"role": "user", "content": full_prompt_for_llm}]
    
    completion_kwargs = {
        "model": MODEL_NAME, 
        "messages": messages, 
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS
    }

    try:
        log.info(f"Requesting HTML design improvement from LiteLLM model: {MODEL_NAME}")
        response = litellm.completion(**completion_kwargs)
        
        if not (response and response.choices and response.choices[0].message and response.choices[0].message.content):
            log.warning("No valid content in LiteLLM response for HTML improvement.")
            return None

        raw_html = response.choices[0].message.content
        cleaned_html = _clean_llm_html_output(raw_html)

        if cleaned_html:
            log.info("Successfully improved and cleaned HTML digest.")
            return cleaned_html
        
        log.warning(f"Could not clean improved HTML from LiteLLM output. Raw: {raw_html[:300]}...")
        return None

    except Exception as e:
        log.error(f"LiteLLM error during HTML design improvement: {e}", exc_info=True)
        return None

def _save_html_to_file(content: str, query_term: str, file_context_name: str, exports_dir: str = "exports") -> None:
    os.makedirs(exports_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_query = "".join(c for c in query_term if c.isalnum()).lower()
    filename = f"{file_context_name}_{sanitized_query}_{timestamp_str}.html"
    filepath = os.path.join(exports_dir, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        log.info(f"Saved improved HTML to: {filepath}")
    except IOError as e:
        log.error(f"Failed to write improved HTML to file {filepath}. Error: {e}")

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

    log.info("--- Running generate_improved_email_design.py test ---")

    if not os.getenv("ANTHROPIC_API_KEY"):
        log.critical("ANTHROPIC_API_KEY not in .env. Test cannot run.")
    else:
        exports_dir = "exports"
        base_html_path = _find_latest_file_by_pattern(exports_dir, "base_digest_html_*.html")

        if not base_html_path:
            log.error("Could not find a base HTML file in 'exports/'.")
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

                improved_html = improve_html_digest_design(base_html)
                
                if improved_html:
                    log.info("HTML design improvement successful for test.")
                    print("\n--- Improved HTML (Snippet) ---")
                    print(improved_html[:1000] + "...")
                    _save_html_to_file(improved_html, query_term, "email_improved_html")
                else:
                    log.error("Failed to improve HTML design during test.")
                    print("\n--- HTML Design Improvement FAILED ---")

            except Exception as e:
                log.error(f"Error during CLI test execution: {e}", exc_info=True)

    log.info("--- generate_improved_email_design.py test finished ---")