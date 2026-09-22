import json
import os
import streamlit as st

def extract_skills_with_llm(jd_text: str) -> list | None:
    """
    Calls Groq API to extract professional and technical skills from the JD.
    Returns a list of skills, or None if API key is missing or limit is reached.
    """
    api_key = None
    try:
        api_key = st.secrets.get("GROQ_API_KEY")
    except Exception:
        # Streamlit secrets might not be configured
        api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        return None

    try:
        from groq import Groq
        client = Groq(api_key=api_key, max_retries=0)
        
        prompt = f"""
        Extract a list of professional and technical skills from the following Job Description.
        Return a JSON object with a single key "skills" containing an array of strings in lowercase. Do not include any other text or markdown blocks.
        
        Job Description:
        {jd_text}
        """

        groq_models = ["llama-3.3-70b-versatile", "groq/openai/gpt-oss-120b", "llama-3.1-8b-instant", "gemma2-9b-it"]
        response = None
        for model_name in groq_models:
            try:
                response = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=model_name,
                    temperature=0.0
                )
                break
            except Exception as e:
                print(f"Groq model {model_name} failed: {e}")
                
        if not response:
            raise Exception("All Groq models failed")
        
        response_text = response.choices[0].message.content.strip()
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
        print(f"Groq API fallback triggered due to error: {e}")
        try:
            import google.generativeai as genai
            gemini_key = None
            try:
                gemini_key = st.secrets.get("GEMINI_API_KEY")
            except Exception:
                gemini_key = os.environ.get("GEMINI_API_KEY")
                
            if not gemini_key:
                print("Gemini API key not found in secrets/environment.")
                return None
                
            genai.configure(api_key=gemini_key)
            gemini_models = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-1.5-flash", "gemini-pro"]
            response = None
            for model_name in gemini_models:
                try:
                    gemini_model = genai.GenerativeModel(model_name)
                    response = gemini_model.generate_content(prompt)
                    break
                except Exception as e:
                    print(f"Gemini model {model_name} failed: {e}")
                    
            if not response:
                print("All Gemini models failed.")
                return None
                
            response_text = response.text.strip()
            
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
        except Exception as gemini_e:
            print(f"Gemini API fallback also failed: {gemini_e}")
            return None

def generate_improvement_tips(target_skills: list, job_title: str, are_missing: bool = True) -> str:
    """
    Calls Groq API to get 2 brief bullet points on how to improve the resume.
    """
    if not target_skills:
        return ""

    api_key = None
    try:
        api_key = st.secrets.get("GROQ_API_KEY")
    except Exception:
        api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        return ""

    try:
        from groq import Groq
        client = Groq(api_key=api_key, max_retries=0)
        
        skills_str = ", ".join(target_skills[:5]) # limit to top 5 to save tokens
        if are_missing:
            prompt = f"User applying for '{job_title}' is missing these skills: {skills_str}. Provide exactly 2 short, actionable bullet points advising which sections (e.g. Experience) to add them to. Keep under 50 words."
        else:
            prompt = f"User applying for '{job_title}' has these skills but low keyword density: {skills_str}. Provide exactly 2 short, actionable bullet points advising how to elaborate on them in their Experience bullet points for better context. Keep under 50 words."

        groq_models = ["llama-3.3-70b-versatile", "groq/openai/gpt-oss-120b", "llama-3.1-8b-instant", "gemma2-9b-it"]
        response = None
        for model_name in groq_models:
            try:
                response = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=model_name,
                    temperature=0.7,
                    max_tokens=80
                )
                break
            except Exception as e:
                print(f"Groq tips model {model_name} failed: {e}")
                
        if not response:
            raise Exception("All Groq models failed")
            
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Groq API tips error: {e}")
        try:
            import google.generativeai as genai
            gemini_key = None
            try:
                gemini_key = st.secrets.get("GEMINI_API_KEY")
            except Exception:
                gemini_key = os.environ.get("GEMINI_API_KEY")
                
            if not gemini_key:
                print("Gemini API key not found in secrets/environment.")
                return ""
                
            genai.configure(api_key=gemini_key)
            gemini_models = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-1.5-flash", "gemini-pro"]
            response = None
            for model_name in gemini_models:
                try:
                    gemini_model = genai.GenerativeModel(model_name)
                    response = gemini_model.generate_content(prompt)
                    break
                except Exception as e:
                    print(f"Gemini tips model {model_name} failed: {e}")
                    
            if not response:
                print("All Gemini models failed.")
                return ""
                
            return response.text.strip()
        except Exception as gemini_e:
            print(f"Gemini API tips fallback error: {gemini_e}")
            return ""

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
