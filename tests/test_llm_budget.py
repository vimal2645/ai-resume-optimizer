import time
import os
from unittest import mock
from core.parser import parse_resume, parse_job_description, classify_skills
from core.role_detector import detect_role
from utils.ai_skill_matcher import ai_matcher, _load_keyword_processor
from utils.dynamic_skills import extract_skills_with_llm, generate_improvement_tips
import json

def test_analyze_budget():
    budget = 30.0
    start_time = time.time()

    print("Running analyze with mocked hanging LLMs...")
    
    # Set fake keys to pass the key check
    os.environ["GROQ_API_KEY"] = "fake_key"
    os.environ["GEMINI_API_KEY"] = "fake_key"

    def slow_mock(*args, **kwargs):
        # simulate hanging for 8s per call
        time.sleep(8)
        raise Exception("Mock Timeout/Hang")

    # We mock _call_llms directly to simulate slow behavior? 
    # Or mock the actual clients. Let's mock the actual clients.
    import groq
    from unittest.mock import MagicMock
    
    with mock.patch("groq.Groq") as MockGroq, \
         mock.patch("google.generativeai.GenerativeModel") as MockGemini:
        
        mock_groq_instance = MagicMock()
        mock_groq_instance.chat.completions.create.side_effect = slow_mock
        MockGroq.return_value = mock_groq_instance
        
        mock_gemini_instance = MagicMock()
        mock_gemini_instance.generate_content.side_effect = slow_mock
        MockGemini.return_value = mock_gemini_instance
        
        # Fake data
        resume_text = "I am a software engineer with Python and React skills."
        job_description = "We need a software engineer with Python, React, and AWS."
        
        kp = _load_keyword_processor()
        archetypes = {"Software Engineer": {"name": "Software Engineer", "keywords": ["python", "react"], "display_name": "SE"}}
        synonym_map = {"aws": "amazon web services"}
        
        job_keywords = parse_job_description(job_description, keyword_processor=kp)
        role_result = detect_role(job_description, archetypes=archetypes, synonym_map=synonym_map)
        archetype_data = role_result["archetype_data"]
        
        score_data = ai_matcher.calculate_enhanced_ats_score(
            resume_skills=["python", "react"],
            job_keywords=job_keywords,
            archetype_data=archetype_data,
            resume_text=resume_text,
            jd_text=job_description,
        )
        
        all_jd_skills = list(dict.fromkeys(
            (job_keywords.get("must_have") or []) +
            (job_keywords.get("nice_to_have") or [])
        ))
        skill_buckets = classify_skills(
            jd_skills=all_jd_skills,
            skills_full=["python", "react"],
            skills_in_skills_section=[],
            synonym_map=synonym_map,
        )
        
        llm_skills = None
        tips = ""
        
        elapsed1 = time.time() - start_time
        print(f"Elapsed before extract_skills: {elapsed1}")
        if elapsed1 < (budget - 8.0):
            llm_skills = extract_skills_with_llm(job_description, start_time, budget)
            if llm_skills is not None:
                pass
                
        elapsed2 = time.time() - start_time
        print(f"Elapsed before generate_tips: {elapsed2}")
        if elapsed2 < (budget - 8.0):
            genuinely_missing = skill_buckets.get("genuinely_missing", [])
            if genuinely_missing:
                tips = generate_improvement_tips(genuinely_missing, job_keywords.get("job_title", "Technical Role"), are_missing=True, start_time=start_time, time_budget=budget)
                
    
    elapsed = time.time() - start_time
    print(f"Total time elapsed: {elapsed:.2f} seconds")
    
    assert elapsed < budget, f"Execution time {elapsed:.2f} exceeded budget {budget}!"
    assert tips == "" or "Align the text structure" in tips, "Should fallback to local tips"
    assert llm_skills is None, "LLM skills should be None due to exceptions"
    print("Test passed! Budget enforced and local fallback returned successfully.")

if __name__ == "__main__":
    test_analyze_budget()
