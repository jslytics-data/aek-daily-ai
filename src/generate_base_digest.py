import logging
import os
import json
import re
import warnings
from datetime import datetime
import glob

import litellm
from dotenv import load_dotenv

litellm.set_verbose = False
log = logging.getLogger(__name__)

ENABLE_LLM_THINKING = True
LLM_THINKING_BUDGET_TOKENS = 32768
TEMPERATURE = 1.0

AEK_NEWSLETTER_HTML_PROMPT = """
You are an expert content creator specializing in sports journalism, with a deep focus on AEK Athens. Your style is similar to Morning Brew - witty, engaging, and insightful.

Your task is to create a daily Email newsletter in email HTML format for today, {formatted_today_date}, based on the provided JSON data of recent news articles.

Key Instructions:
- **Output Language:** The newsletter must be in Greek (el).
- **Newsletter Name:** The name is "AEK Daily".
- **Tone & Style:** Maintain a natural, knowledgeable, and slightly sarcastic tone. Avoid cringy greetings. The tone should be that of a dedicated fan and deep knowledge journalist who has read all the news. Use emojis sparingly and only where they add value.
- **Content Focus:** Focus exclusively on AEK. Exclude or downplay tangentially related news.
- **Readability:** Use formatting (headings, lists, bold text) extensively to enhance readability. Vary sentence structure for a natural flow. Ensure the content is accessible to both die-hard fans and casual readers.
- **HTML Format:** Output a complete, mobile-friendly email HTML document. Minimize side margins to maximize text space on mobile devices. Use beautifyl, simple, clean design and avoid dark backgrounds. Do not include images.
- **Structure:** If there is enough content, start with a "Highlights" bullet-point section. This is great for grabbing attention. You can use the word "Highlights", its universally understood.
- **Sourcing:** Reference sources by linking inline where appropriate, giving credit to the original journalists. Prioritize reputable and team-friendly sources.
"""

HTML_FULL_DOCUMENT_ONLY_INSTRUCTION = """
IMPORTANT: Your output MUST be ONLY a single, complete HTML document.
Do NOT include any additional text, explanations, or comments outside of the HTML code itself.
"""

def _get_day_with_suffix(day: int) -> str:
    if 11 <= day <= 13:
        return f"{day}th"
    suffixes = {1: 'st', 2: 'nd', 3: 'rd'}
    return f"{day}{suffixes.get(day % 10, 'th')}"

def _get_formatted_today_date() -> str:
    now = datetime.now()
    day_with_suffix = _get_day_with_suffix(now.day)
    return now.strftime(f"%A, {day_with_suffix} %B %Y")

def _clean_llm_html_output(raw_html_text: str) -> str | None:
    if not raw_html_text or not isinstance(raw_html_text, str):
        return None
    cleaned_text = raw_html_text.strip()
    start_match = re.search(r"<!DOCTYPE\s+html|<html", cleaned_text, re.IGNORECASE)
    if not start_match:
        log.warning("Could not find standard HTML start in LLM output.")
        return cleaned_text if cleaned_text.startswith("<") and cleaned_text.endswith(">") else None
    
    start_index = start_match.start()
    last_end_tag_index = cleaned_text.rfind("</html>")
    if last_end_tag_index == -1:
        log.warning("Could not find standard HTML end or it's malformed.")
        return cleaned_text[start_index:].strip()
        
    return cleaned_text[start_index : last_end_tag_index + len("</html>")].strip()

def generate_base_html_digest(query_term: str, articles_data_list: list[dict]) -> str | None:
    log.info(f"Generating base HTML digest for query: '{query_term}' with {len(articles_data_list)} articles.")
    model_string = os.getenv("LITELLM_MODEL_STRING")
    if not model_string:
        log.error("LITELLM_MODEL_STRING not found in environment.")
        return None

    if not articles_data_list:
        log.warning("No articles data provided for HTML digest generation.")
        return None

    formatted_today = _get_formatted_today_date()
    final_user_prompt = AEK_NEWSLETTER_HTML_PROMPT.format(formatted_today_date=formatted_today)
    
    articles_json_content_string = json.dumps(articles_data_list, indent=2, ensure_ascii=False)
    full_user_content_for_html = (
        f"{final_user_prompt}\n\n"
        f"{HTML_FULL_DOCUMENT_ONLY_INSTRUCTION}\n\n"
        f"--- Attached JSON Data (articles with full text) ---\n"
        f"```json\n{articles_json_content_string}\n```"
    )
    
    messages = [{"role": "user", "content": full_user_content_for_html}]

    completion_kwargs = {"model": model_string, "messages": messages, "temperature": TEMPERATURE}
    if ENABLE_LLM_THINKING:
        completion_kwargs["thinking"] = {"type": "enabled", "budget_tokens": LLM_THINKING_BUDGET_TOKENS}
        log.info(f"LLM thinking enabled with token budget: {LLM_THINKING_BUDGET_TOKENS}")

    try:
        log.info(f"Requesting HTML digest from LiteLLM model: {model_string}")
        response = litellm.completion(**completion_kwargs)
        if response and response.choices and response.choices[0].message and response.choices[0].message.content:
            raw_html = response.choices[0].message.content
            cleaned_html = _clean_llm_html_output(raw_html)
            if cleaned_html:
                log.info("Successfully generated and cleaned HTML digest.")
                return cleaned_html
            log.warning(f"Could not clean HTML from LiteLLM output. Raw: {raw_html[:300]}...")
            return None
        log.warning("No valid content in LiteLLM response for HTML generation.")
        return None
    except Exception as e:
        log.error(f"LiteLLM error during HTML generation: {e}", exc_info=True)
        return None

def save_text_to_file(content: str, query_term: str, file_context_name: str, extension: str, exports_dir: str = "exports") -> str | None:
    os.makedirs(exports_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_query = "".join(c for c in query_term if c.isalnum()).lower()
    filename = f"{file_context_name}_{sanitized_query}_{timestamp_str}.{extension}"
    filepath = os.path.join(exports_dir, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        log.info(f"Saved content to: {filepath}")
        return filepath
    except IOError as e:
        log.error(f"Failed to write to file {filepath}. Error: {e}")
        return None

def find_latest_input_file(search_dir: str, pattern_prefix: str) -> str | None:
    search_pattern = os.path.join(search_dir, f"{pattern_prefix}_*.json")
    try:
        list_of_files = glob.glob(search_pattern)
        return max(list_of_files, key=os.path.getctime) if list_of_files else None
    except Exception as e:
        log.error(f"Error finding input file in {search_dir} with pattern {pattern_prefix}: {e}")
        return None

if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    log.info("--- Running generate_base_digest.py test ---")

    if not os.getenv("GEMINI_API_KEY") or not os.getenv("LITELLM_MODEL_STRING"):
        log.critical("GEMINI_API_KEY or LITELLM_MODEL_STRING not in .env. Test cannot run.")
    else:
        exports_directory = "exports"
        input_file_path = find_latest_input_file(exports_directory, "orchestrated_articles")

        if not input_file_path:
            log.error(f"No orchestrated articles file found in '{exports_directory}'.")
            log.error("Please run 'content_retrieval.orchestrator' first.")
        else:
            log.info(f"Using input file: {input_file_path}")
            try:
                with open(input_file_path, 'r', encoding='utf-8') as f:
                    articles_for_digest = json.load(f)
                
                filename_parts = os.path.basename(input_file_path).split('_')
                test_query_term = "testquery"
                if len(filename_parts) > 2 and filename_parts[0] == "orchestrated" and filename_parts[1] == "articles":
                    test_query_term = filename_parts[2]

                log.info(f"Extracted query term for test: {test_query_term}")

                log.info("--- Generating Base HTML Digest ---")
                base_html = generate_base_html_digest(test_query_term, articles_for_digest)
                if base_html:
                    log.info("Base HTML digest generated successfully for test.")
                    print("\n--- Base HTML Digest (Snippet) ---")
                    print(base_html[:1000] + "...")
                    save_text_to_file(base_html, test_query_term, "base_digest_html", "html")
                else:
                    log.error("Failed to generate base HTML digest during test.")
                    print("\n--- Base HTML Digest Generation FAILED ---")

            except Exception as e:
                log.error(f"Error during CLI test execution: {e}", exc_info=True)

    log.info("--- generate_base_digest.py test finished ---")