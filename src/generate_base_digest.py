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

NEWSLETTER_PROMPT_GENERATION_INSTRUCTION_TEMPLATE = """
     Based on the below JSON content, generate an optimised prompt for another LLM to create an AI newsletter.
        Fill out the info below after studying the provided JSON. Don't alter it a lot, I want this to be the prompt, just very slightly adjusted based on the content at hand. Alter only if you think its absolutely critical.

        The base GUIDELINE prompt is:
        -topic title: {{generate this from json}}
        -topic description: {{generate this from json}}
        - Based on the attached articles' metadata, I want you to create a daily newsletter page for today, {formatted_today_date}.
        - Should be similar style to Morning Brew.
        - The name is "{{{{topic}}}} Daily" ("Daily" should be like this in English, even if language is other. So for example, it shoulbe "Χίος Daily")
        - Output content in source language of the provided article titles.
        - Exclude articles not related to {{{{topic}}}}. Careful to only focus on the topic.
        - Reference links inline wherever useful to users. Good to give credit to the journalists and platforms, but not too intrusive for our users. Prioritise linking topical and high reputable relevant sources. Try not to show sources/links from opposing sources. For example if the newsletter is about Manchester United, don’t show links from an Arsenal or London domain, unless there's clear value(e.g. tickets, fixture etc). Generally give priority to latest articles.
        - Output in nicely formatted modern email HTML, like Modern Brew. Make sure its mobile friendly. For mobile views, minimise side margin so to maximise text space.
        - Follow the topic’s colors, but don't overdo it.
        - Try to mimic the tone suggested by the article titles. Don’t be cringy. Don’t overdo with greeting, you can get straight to it. Make the tone natural as if a human topic journalist with deep knowledge and native style and tone would edit it. If you really think it helps, use Emoji's but don't overdo it. Keep in mind that a portion of the audience would have already read the headlines online, so maybe include interesting details if you find them, so there's value for them as well.
        - Enhance Readability: Ensure text is clear and concise. Vary sentence structure for natural flow, and use subheadings to break up content, making it scannable and easy to digest. Think nuance, think of neuroscience and serotonin and dopamine. Use formatting extensively to improve readability.
        - Make the UI like a world class UI designer would design it, but keep it simple. Add in some magic!
        - Do not include images

        ONLY output the new, optimised prompt itself, NOT the JSON file content. The optimised prompt should be ready to be used by another LLM, which will be given the full article texts separately.
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

def _create_digest_llm_prompt(articles_metadata_list: list[dict]) -> str | None:
    log.info(f"Creating digest LLM prompt for {len(articles_metadata_list)} articles.")
    model_string = os.getenv("LITELLM_MODEL_STRING")
    if not model_string:
        log.error("LITELLM_MODEL_STRING not found in environment.")
        return None

    if not articles_metadata_list:
        log.warning("No article metadata provided for prompt generation.")
        return None

    try:
        metadata_for_prompt = [{"title": a.get("title"), "publication_date": a.get("publication_date"), 
                                "source_domain": a.get("source_domain"), "link": a.get("link")} 
                               for a in articles_metadata_list]
        articles_json_string = json.dumps(metadata_for_prompt, indent=2, ensure_ascii=False)
    except Exception as e:
        log.error(f"Error preparing article metadata for prompt generation: {e}")
        return None

    formatted_today = _get_formatted_today_date()
    instruction = NEWSLETTER_PROMPT_GENERATION_INSTRUCTION_TEMPLATE.format(formatted_today_date=formatted_today)
    full_meta_prompt = f"{instruction}\n\nJSON Article Metadata:\n```json\n{articles_json_string}\n```"
    messages = [{"role": "user", "content": full_meta_prompt}]

    completion_kwargs = {"model": model_string, "messages": messages, "temperature": TEMPERATURE}
    if ENABLE_LLM_THINKING:
        completion_kwargs["thinking"] = {"type": "enabled", "budget_tokens": LLM_THINKING_BUDGET_TOKENS}
        log.info(f"LLM thinking enabled with token budget: {LLM_THINKING_BUDGET_TOKENS}")

    try:
        log.info(f"Requesting optimised prompt from LiteLLM model: {model_string}")
        response = litellm.completion(**completion_kwargs)
        if response and response.choices and response.choices[0].message and response.choices[0].message.content:
            optimised_prompt = response.choices[0].message.content.strip()
            log.info("Successfully generated optimised prompt.")
            return optimised_prompt
        log.warning("No valid content in LiteLLM response for prompt generation.")
        return None
    except Exception as e:
        log.error(f"LiteLLM error during prompt generation: {e}", exc_info=True)
        return None

def generate_base_html_digest(query_term: str, articles_data_list: list[dict]) -> str | None:
    log.info(f"Generating base HTML digest for query: '{query_term}' with {len(articles_data_list)} articles.")
    model_string = os.getenv("LITELLM_MODEL_STRING")
    if not model_string:
        log.error("LITELLM_MODEL_STRING not found in environment.")
        return None

    if not articles_data_list:
        log.warning("No articles data provided for HTML digest generation.")
        return None

    optimised_prompt = _create_digest_llm_prompt(articles_data_list)
    if not optimised_prompt:
        log.error("Failed to generate optimised prompt, cannot proceed with HTML generation.")
        return None

    final_user_prompt = optimised_prompt + HTML_FULL_DOCUMENT_ONLY_INSTRUCTION
    articles_json_content_string = json.dumps(articles_data_list, indent=2, ensure_ascii=False)
    full_user_content_for_html = f"{final_user_prompt}\n\nAttached JSON Data (articles with full text):\n```json\n{articles_json_content_string}\n```"
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

                log.info("--- Test Part 1: Generating Optimised Prompt ---")
                generated_optimised_prompt = _create_digest_llm_prompt(articles_for_digest)
                if generated_optimised_prompt:
                    log.info("Optimised prompt generated successfully for test.")
                    print("\n--- Optimised Prompt (Snippet) ---")
                    print(generated_optimised_prompt[:500] + "...")
                    save_text_to_file(generated_optimised_prompt, test_query_term, "optimised_digest_prompt", "txt")
                else:
                    log.error("Failed to generate optimised prompt during test.")
                    print("\n--- Optimised Prompt Generation FAILED ---")

                log.info("--- Test Part 2: Generating Base HTML Digest ---")
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