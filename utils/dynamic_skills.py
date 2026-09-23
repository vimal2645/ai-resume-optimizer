import json
import os
import streamlit as st

GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-20b",
]

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-pro",
]

def get_key(name):
    try:
        return st.secrets[name]
    except Exception:
        return os.getenv(name)

def _call_llms(prompt, is_extraction=True, start_time=None, time_budget=30.0):
    """
    Helper to execute LLM calls with budgets, trying Groq then Gemini.
    """
    max_tokens = 800 if is_extraction else 250
    temperature = 0.0 if is_extraction else 0.7
    timeout = 7.0

    import time
    def _time_exceeded():
        if start_time is None:
            return False
        return (time.time() - start_time) >= (time_budget - 8.0) # buffer of 8 seconds for the next call timeout

    # 1. Try Groq (Max 2 models)
    groq_key = get_key("GROQ_API_KEY")
    if groq_key and not _time_exceeded():
        try:
            from groq import Groq
            import groq
            client = Groq(api_key=groq_key, max_retries=0, timeout=timeout)
            
            for i in range(min(2, len(GROQ_MODELS))):
                if _time_exceeded():
                    break
                model_name = GROQ_MODELS[i]
                try:
                    response = client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model=model_name,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    return response.choices[0].message.content.strip()
                except (groq.InternalServerError, groq.RateLimitError, groq.APIConnectionError, groq.APITimeoutError) as e:
                    # Silently skip on standard transient errors to avoid console spam
                    continue
                except Exception as e:
                    # Silently break on auth/not_found errors
                    break
        except Exception as init_err:
            pass

    # 2. Try Gemini (Max 2 models)
    gemini_key = get_key("GEMINI_API_KEY")
    if gemini_key and not _time_exceeded():
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            
            for i in range(min(2, len(GEMINI_MODELS))):
                if _time_exceeded():
                    break
                model_name = GEMINI_MODELS[i]
                try:
                    gemini_model = genai.GenerativeModel(model_name)
                    response = gemini_model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=temperature,
                            max_output_tokens=max_tokens,
                        ),
                        request_options={"timeout": timeout}
                    )
                    return response.text.strip()
                except Exception as e:
                    err_str = str(e).lower()
                    if "api_key" in err_str or "permission" in err_str or "unauthorized" in err_str:
                        break
                    continue
        except Exception as init_err:
            pass

    return None

def extract_skills_with_llm(jd_text: str, start_time=None, time_budget=30.0) -> list | None:
    """
    Calls LLM API to extract professional and technical skills from the JD.
    Returns a list of skills, or None if API key is missing or limit is reached.
    """
    prompt = f"""
    Extract a list of professional and technical skills from the following Job Description.
    Return a JSON object with a single key "skills" containing an array of strings in lowercase. Do not include any other text or markdown blocks.
    
    Job Description:
    {jd_text}
    """

    response_text = _call_llms(prompt, is_extraction=True, start_time=start_time, time_budget=time_budget)
    if not response_text:
        return None
        
    try:
        # Clean up markdown code blocks if the model ignored instructions
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.lower().startswith("json"):
                response_text = response_text[4:].strip()
                
        data = json.loads(response_text)
        
        new_skills = []
        if isinstance(data, list):
            new_skills = data
        elif isinstance(data, dict):
            for val in data.values():
                if isinstance(val, list):
                    new_skills.extend(val)
                    
        return [str(s).lower() for s in new_skills]
    except Exception as e:
        # Failed to parse JSON, silently fallback to local
        return None

def generate_improvement_tips(target_skills: list, job_title: str, are_missing: bool = True, start_time=None, time_budget=30.0) -> str:
    """
    Calls LLM API to get 2 brief bullet points on how to improve the resume.
    Provides standard TF-IDF alignment tips if the LLM fails.
    """
    fallback_tips = (
        "- Align the text structure of your resume to closely match the job description.\n"
        "- Talk relevantly about all your skills to ensure strong keyword context for TF-IDF algorithms."
    )

    if not target_skills:
        return fallback_tips

    skills_str = ", ".join(target_skills[:5]) # limit to top 5 to save tokens
    if are_missing:
        prompt = f"User applying for '{job_title}' is missing these skills: {skills_str}. Provide exactly 2 short, actionable bullet points advising which sections (e.g. Experience) to add them to. Keep under 50 words."
    else:
        prompt = f"User applying for '{job_title}' has these skills but low keyword density: {skills_str}. Provide exactly 2 short, actionable bullet points advising how to elaborate on them in their Experience bullet points for better context. Keep under 50 words."

    response_text = _call_llms(prompt, is_extraction=False, start_time=start_time, time_budget=time_budget)
    if not response_text:
        return fallback_tips
    
    return response_text

def update_local_db(new_skills: list):
    """
    Appends genuinely new skills to the local skills_db.json file for future offline use.
    """
    if not new_skills:
        return
        
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base, "data", "skills_db.json")
    
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            skills_db = json.load(f)
            
        initial_len = len(skills_db)
        
        # Add new skills, keeping it case-insensitive unique
        existing_lower = {s.lower() for s in skills_db}
        for skill in new_skills:
            if skill.lower() not in existing_lower:
                skills_db.append(skill.lower())
                existing_lower.add(skill.lower())
                
        if len(skills_db) > initial_len:
            with open(db_path, "w", encoding="utf-8") as f:
                json.dump(skills_db, f, indent=2)
            print(f"Added {len(skills_db) - initial_len} new skills to local database.")
    except Exception as e:
        print(f"Failed to update local DB: {e}")
