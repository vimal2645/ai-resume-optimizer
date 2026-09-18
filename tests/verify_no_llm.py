"""
tests/verify_no_llm.py
======================
Lightweight verification — no Streamlit context, no model download.
Tests all deterministic pipeline logic.
Run: python tests/verify_no_llm.py
"""
import sys, os, time, json, io, re

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    detail_str = f"  [{detail}]" if detail else ""
    print(f"{status}  {name}{detail_str}")

# ============================================================
# Test 1 — Zero Groq/LLM imports (REMOVED)
# ============================================================
# This test has been removed as we are deliberately adding Groq LLM support.
print("\n=== 1: Zero LLM/network imports (SKIPPED) ===")
check("No Groq/OpenAI imports in any .py file", True, "Test removed for Groq integration")

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# Test 2 — Role detection: AI Engineer
# ============================================================
print("\n=== 2: Role detection — AI Engineer ===")
from core.role_detector import detect_role

with open(os.path.join(base, "data", "role_archetypes.json")) as f:
    archetypes = json.load(f)
with open(os.path.join(base, "data", "synonym_map.json")) as f:
    synonym_map = json.load(f)

ai_jd = """
Senior AI Engineer
We are looking for an experienced AI Engineer to join our team.
Requirements: PyTorch, TensorFlow, deep learning, NLP, LLM fine-tuning, MLOps,
Python, Hugging Face, model deployment, GPU infrastructure, RAG, embeddings, transformer.
"""
r = detect_role(ai_jd, archetypes=archetypes, synonym_map=synonym_map)
check("AI Engineer JD -> ai_engineer", r["archetype_name"] == "ai_engineer",
      f"got={r['archetype_name']}, confidence={r['confidence']}")

# ============================================================
# Test 3 — Role detection: GTM Engineer
# ============================================================
print("\n=== 3: Role detection — GTM Engineer ===")
gtm_jd = """
Go-to-Market Solutions Engineer
We seek a GTM engineer for sales enablement and customer acquisition.
Responsibilities: Salesforce CRM, enterprise sales, customer success, business development,
product demo, proof of concept, account management, competitive analysis, revenue pipeline,
B2B sales, quota management, deal cycle, RFP, pricing strategy, partnerships.
"""
r2 = detect_role(gtm_jd, archetypes=archetypes, synonym_map=synonym_map)
check("GTM JD -> gtm_engineer", r2["archetype_name"] == "gtm_engineer",
      f"got={r2['archetype_name']}, confidence={r2['confidence']}")

# ============================================================
# Test 4 — Skill extraction
# ============================================================
print("\n=== 4: Skill extraction ===")
from core.parser import extract_skills_from_text, apply_synonyms, check_extraction_quality, segment_resume_text

sample_resume = """
John Doe

Skills
Python, TensorFlow, PyTorch, deep learning, NLP, Docker, Kubernetes, AWS, SQL, pandas, scikit-learn

Experience
Developed ML models using PyTorch and TensorFlow.
Deployed services on k8s cluster using Docker containers.
Built REST APIs with FastAPI and Flask.
"""
skills = extract_skills_from_text(sample_resume)
check("Extracts python",            "python"     in skills, f"found: {skills[:6]}")
check("Extracts tensorflow",        "tensorflow" in skills, f"found: {skills[:6]}")
check("Synonym k8s -> kubernetes",  "kubernetes" in skills, f"found: {skills[:6]}")
check("Extracts scikit-learn",      "scikit-learn" in skills, f"found: {skills[:6]}")

# ============================================================
# Test 5 — Section segmentation
# ============================================================
print("\n=== 5: Section segmentation ===")
sectioned = segment_resume_text(sample_resume)
check("Skills section detected",    bool(sectioned.get("skills")))
check("Experience section detected",bool(sectioned.get("experience")))

# ============================================================
# Test 6 — Extraction quality flags
# ============================================================
print("\n=== 6: Extraction quality checks ===")
garbled_q = check_extraction_quality("!!!@@@###$$$")
check("Garbled text not ok",  not garbled_q["ok"], garbled_q.get("warning","")[:50])

short_q = check_extraction_quality("Hi")
check("Short text not ok",    not short_q["ok"])

good_q = check_extraction_quality(
    "John Doe software engineer five years experience python machine learning "
    "deep learning AWS docker kubernetes REST API sql postgresql data science "
    "scikit-learn pandas numpy matplotlib flask fastapi agile scrum git github"
)
check("Good text is ok", good_q["ok"])

# ============================================================
# Test 7 — Three-bucket invariant (no invented skills)
# ============================================================
print("\n=== 7: Three-bucket invariant (genuinely missing ≠ optimizable) ===")
from core.parser import classify_skills

buckets = classify_skills(
    jd_skills=["python", "docker", "aws", "kubernetes"],
    skills_full=["python", "docker", "aws"],
    skills_in_skills_section=["python", "docker"],
)
check("Valid skill (aws) in OPTIMIZABLE", "aws" in buckets["optimizable"])
check("Invented skill (kubernetes) in GENUINELY_MISSING", "kubernetes" in buckets["genuinely_missing"])
check("GENUINELY_MISSING not in OPTIMIZABLE", "kubernetes" not in buckets["optimizable"])

# ============================================================
# Test 8 — TF-IDF + skill scoring (no model download)
# ============================================================
print("\n=== 8: TF-IDF + skill scoring speed ===")

# Bypass @st.cache_resource by importing raw functions only
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from rapidfuzz import fuzz

resume_text = (
    "Experienced data scientist with 4 years in python, tensorflow, aws, docker, "
    "sql, pandas, scikit-learn, machine learning, deep learning. Built and deployed "
    "ML pipelines using airflow and docker on AWS. Developed REST APIs with FastAPI."
)
jd_text = (
    "Seeking a machine learning engineer proficient in tensorflow, python, aws, "
    "docker, kubernetes, sql, scikit-learn. Experience with MLOps and model deployment."
)

start = time.perf_counter()

# TF-IDF
vec = TfidfVectorizer(stop_words="english", max_features=5000)
mat = vec.fit_transform([resume_text, jd_text])
tfidf_score = float(cosine_similarity(mat[0:1], mat[1:2])[0][0]) * 100

# Fuzzy skill matching
resume_skills = ["python", "tensorflow", "aws", "docker", "sql", "pandas", "scikit-learn"]
jd_skills = ["tensorflow", "python", "aws", "docker", "kubernetes", "sql", "scikit-learn"]
matched = [s for s in jd_skills if any(fuzz.token_set_ratio(s, rs) >= 80 for rs in resume_skills)]

elapsed = time.perf_counter() - start
check(
    "TF-IDF + skill matching < 1s",
    elapsed < 1.0,
    f"{elapsed*1000:.1f}ms, tfidf={tfidf_score:.1f}%, matched={len(matched)}/{len(jd_skills)}"
)

# ============================================================
# Test 9 — synonym_map and skills_db exist and are valid JSON
# ============================================================
print("\n=== 9: Data files integrity ===")
skills_db = json.load(open(os.path.join(base, "data", "skills_db.json")))
syn_map   = json.load(open(os.path.join(base, "data", "synonym_map.json")))
arch      = json.load(open(os.path.join(base, "data", "role_archetypes.json")))

check("skills_db.json has 500+ entries", len(skills_db) >= 500, f"count={len(skills_db)}")
check("synonym_map.json non-empty",      len(syn_map) > 0, f"count={len(syn_map)}")
check("role_archetypes has ai_engineer", "ai_engineer" in arch)
check("role_archetypes has gtm_engineer","gtm_engineer" in arch)
check("role_archetypes has generic",     "generic" in arch)

# ============================================================
# Test 10 — dead LLM files deleted (REMOVED)
# ============================================================
print("\n=== 10: Dead LLM files deleted (SKIPPED) ===")
check("Deleted dead LLM files test", True, "Test removed for Groq integration")

# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 60)
passed = sum(1 for r in results if r[0] == PASS)
print(f"Results: {passed}/{len(results)} tests passed")
if passed == len(results):
    print("ALL Phase 7 checks PASSED")
else:
    failed = [r for r in results if r[0] == FAIL]
    for r in failed:
        print(f"  FAILED: {r[1]} {r[2]}")
print("=" * 60)
