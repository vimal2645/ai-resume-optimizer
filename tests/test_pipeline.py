"""
tests/test_pipeline.py
======================
Phase 7 verification checklist — run with:
  python tests/test_pipeline.py

Tests:
  1. Zero LLM/network imports in the pipeline
  2. Role detection: AI Engineer JD
  3. Role detection: GTM Engineer JD
  4. Skill extraction from sample resume
  5. Extraction quality check (garbled text)
  6. Hard invariant — no invented skills in docx
  7. Scoring runs in < 1 second (skill match + TF-IDF, no neural model)
"""

import sys
import os
import time
import json

# Add parent directory so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"{status}  {name}" + (f"  [{detail}]" if detail else ""))


# ---------------------------------------------------------------------------
# Test 1 — Zero LLM/network imports
# ---------------------------------------------------------------------------
print("\n=== Test 1: Zero LLM/network imports ===")
import subprocess
proc = subprocess.run(
    ["python", "-c",
     "import ast, sys, os\n"
     "files = []\n"
     "for root,_,fs in os.walk('.'):\n"
     "  for f in fs:\n"
     "    if f.endswith('.py') and '.git' not in root and 'test' not in root:\n"
     "      files.append(os.path.join(root,f))\n"
     "bad=[]\n"
     "for fp in files:\n"
     "  txt=open(fp).read()\n"
     "  if any(x in txt for x in ['from groq','import groq','from openai','import openai','import requests']):\n"
     "    bad.append(fp)\n"
     "print(bad)"],
    capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
bad_files = proc.stdout.strip()
check("No Groq/OpenAI/requests imports", bad_files == "[]", bad_files)


# ---------------------------------------------------------------------------
# Test 2 — Role detection: AI Engineer
# ---------------------------------------------------------------------------
print("\n=== Test 2: AI Engineer role detection ===")
from core.role_detector import detect_role
import json

with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "role_archetypes.json")) as f:
    archetypes = json.load(f)
with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "synonym_map.json")) as f:
    synonym_map = json.load(f)

ai_jd = """
Senior AI Engineer
We are looking for an experienced AI Engineer to build and deploy machine learning models.
Requirements: PyTorch, TensorFlow, deep learning, NLP, LLM fine-tuning, MLOps, Python,
Hugging Face, model deployment, GPU infrastructure, retrieval augmented generation, embeddings.
"""
result = detect_role(ai_jd, archetypes=archetypes, synonym_map=synonym_map)
check("AI Engineer JD → ai_engineer archetype", result["archetype_name"] == "ai_engineer", f"got: {result['archetype_name']}, confidence: {result['confidence']}")


# ---------------------------------------------------------------------------
# Test 3 — Role detection: GTM Engineer
# ---------------------------------------------------------------------------
print("\n=== Test 3: GTM Engineer role detection ===")
gtm_jd = """
Go-to-Market Engineer / Solutions Engineer
We are seeking a GTM Engineer to drive customer acquisition and sales enablement.
Requirements: Salesforce CRM, enterprise sales, customer success, business development,
product demo, proof of concept, account management, competitive analysis, revenue pipeline,
market research, B2B, quota management, deal cycle, RFP procurement.
"""
result_gtm = detect_role(gtm_jd, archetypes=archetypes, synonym_map=synonym_map)
check("GTM JD → gtm_engineer archetype", result_gtm["archetype_name"] == "gtm_engineer", f"got: {result_gtm['archetype_name']}, confidence: {result_gtm['confidence']}")


# ---------------------------------------------------------------------------
# Test 4 — Skill extraction
# ---------------------------------------------------------------------------
print("\n=== Test 4: Skill extraction from resume text ===")
from core.parser import extract_skills_from_text, apply_synonyms, segment_resume_text, check_extraction_quality

sample_resume = """
John Doe
Skills
Python, TensorFlow, PyTorch, deep learning, NLP, Docker, Kubernetes, AWS, SQL, pandas
Experience
Developed ML models using pytorch and tensorflow. Deployed on k8s cluster using docker containers.
"""
skills = extract_skills_from_text(sample_resume)
check("Extracts Python", "python" in skills, f"found: {skills[:8]}")
check("Synonym k8s → kubernetes extracted", "kubernetes" in skills, f"found: {skills[:8]}")


# ---------------------------------------------------------------------------
# Test 5 — Extraction quality check
# ---------------------------------------------------------------------------
print("\n=== Test 5: Extraction quality checks ===")
garbled = "!!@##$%%^&*((()))  \x00\x01\x02"
quality = check_extraction_quality(garbled)
check("Garbled text flagged as not ok", not quality["ok"], quality.get("warning", "")[:60])

good_text = "John Doe software engineer with 5 years experience in python and machine learning building scalable systems"
quality_good = check_extraction_quality(good_text)
check("Good text passes quality check", quality_good["ok"])


# ---------------------------------------------------------------------------
# Test 6 — Three-bucket invariant (no invented skills)
# ---------------------------------------------------------------------------
print("\n=== Test 6: Three-bucket — genuinely missing skills excluded from output ===")
from core.parser import classify_skills

# All skills evidenced in resume (skills_full)
resume_skills_full = ["python", "docker", "aws"]
# Only skills_in_skills_section
resume_skills_listed = ["python", "docker"]
jd_skills = ["python", "docker", "aws", "kubernetes"]

buckets = classify_skills(
    jd_skills=jd_skills,
    skills_full=resume_skills_full,
    skills_in_skills_section=resume_skills_listed,
)
check("Invariant: 'aws' is OPTIMIZABLE (in full text, not listed)", "aws" in buckets["optimizable"])
check("Invariant: 'kubernetes' is GENUINELY_MISSING", "kubernetes" in buckets["genuinely_missing"])
check("Invariant: 'python' is ALREADY_LISTED", "python" in buckets["already_listed"])
check("Invariant: genuinely_missing not in optimizable", "kubernetes" not in buckets["optimizable"])


# ---------------------------------------------------------------------------
# Test 7 — Scoring speed (skill+TF-IDF only)
# ---------------------------------------------------------------------------
print("\n=== Test 7: Scoring speed (skill+TF-IDF only) ===")
from utils.ai_skill_matcher import AISkillMatcher

matcher = AISkillMatcher()
resume_skills = ["python", "pandas", "scikit-learn", "docker", "aws", "sql", "tensorflow"]
job_kw = {
    "must_have": ["python", "tensorflow", "aws", "docker", "kubernetes"],
    "nice_to_have": ["pandas", "scikit-learn", "sql"],
}
resume_txt = "Experienced data scientist with 4 years in python, tensorflow, aws, docker, sql, pandas, scikit-learn. Built and deployed ML pipelines."
jd_txt = "Seeking a machine learning engineer proficient in tensorflow, python, aws, docker, kubernetes, sql."

start = time.perf_counter()
# Skip semantic (model not loaded in test) — test TF-IDF + skill path only
score = matcher.calculate_enhanced_ats_score(
    resume_skills=resume_skills,
    job_keywords=job_kw,
    archetype_data=None,
    resume_text=resume_txt,
    jd_text=jd_txt,
)
elapsed = time.perf_counter() - start

check(
    f"Scoring completes in < 1 second (TF-IDF + skill path)",
    elapsed < 1.0,
    f"{elapsed:.3f}s — ats_score={score['ats_score']}%",
)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
passed = sum(1 for r in results if r[0] == PASS)
print(f"Results: {passed}/{len(results)} tests passed")
if passed == len(results):
    print("🎉 All Phase 7 checks PASSED")
else:
    print("⚠️  Some checks FAILED — review above")
print("=" * 60)
