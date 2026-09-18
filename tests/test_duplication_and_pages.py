"""
tests/test_duplication_and_pages.py
=====================================
Verifies the duplication bug fix and page-length control feature.

Tests:
  1. Name appears exactly once in generated document
  2. Each section heading appears at most once
  3. Experience, projects, certs, education each appear at most once
  4. 1-page budget caps roles, bullets, and projects
  5. 2-page budget allows more content
  6. Trim loop removes lowest-overlap bullet, not highest
  7. assert_no_duplicate_sections raises AssertionError on real duplication

Run: python tests/test_duplication_and_pages.py
"""

import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docx import Document

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    detail_str = f"  [{detail}]" if detail else ""
    print(f"{status}  {name}{detail_str}")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_RESUME_TEXT = """
John Smith
Senior Software Engineer
john.smith@email.com | +91-9876543210 | linkedin.com/in/johnsmith | github.com/johnsmith

Summary
Experienced engineer with 5+ years building scalable systems.

Skills
Python, Django, FastAPI, PostgreSQL, Redis, Docker, Kubernetes, AWS, React, TypeScript

Experience
Senior Software Engineer | TechCorp Ltd
January 2022 - Present
• Built a distributed microservices platform using Python and Kubernetes
• Designed REST APIs with FastAPI serving 50,000 requests/day
• Implemented Redis caching reducing latency by 40%
• Led a team of 4 engineers and conducted code reviews

Software Engineer | StartupXYZ
March 2020 - December 2021
• Developed Django backend for SaaS platform with 10,000 users
• Integrated AWS S3 and CloudFront for media storage
• Wrote unit tests achieving 85% coverage

Junior Developer | WebAgency
June 2018 - February 2020
• Built React frontend components using TypeScript
• Contributed to PostgreSQL schema design
• Fixed bugs and improved performance

Projects
Resume Optimizer Tool
• Built a FlashText-based skill extractor processing 1,000 resumes/minute
• Deployed on Streamlit Cloud with zero API costs
• Achieved 95% accuracy vs LLM baseline

Portfolio Website
• Designed and built personal site using React and TypeScript
• Hosted on AWS with CloudFront CDN

Analytics Dashboard
• Created interactive dashboard with Plotly and Pandas
• Connected to PostgreSQL data warehouse

Crypto Tracker
• Real-time crypto price dashboard using WebSocket and Redis

Certifications
AWS Certified Solutions Architect
Google Cloud Professional Data Engineer
Kubernetes Administrator (CKA)
Docker Certified Associate

Education
B.Tech Computer Science | IIT Delhi
2018 | CGPA: 8.9/10
"""

SAMPLE_SECTIONS = {
    "summary": "Experienced engineer with 5+ years building scalable systems.",
    "skills": "Python, Django, FastAPI, PostgreSQL, Redis, Docker, Kubernetes, AWS, React, TypeScript",
    "experience": """Senior Software Engineer | TechCorp Ltd
January 2022 - Present
• Built a distributed microservices platform using Python and Kubernetes
• Designed REST APIs with FastAPI serving 50,000 requests/day
• Implemented Redis caching reducing latency by 40%
• Led a team of 4 engineers and conducted code reviews

Software Engineer | StartupXYZ
March 2020 - December 2021
• Developed Django backend for SaaS platform with 10,000 users
• Integrated AWS S3 and CloudFront for media storage
• Wrote unit tests achieving 85% coverage

Junior Developer | WebAgency
June 2018 - February 2020
• Built React frontend components using TypeScript
• Contributed to PostgreSQL schema design
• Fixed bugs and improved performance""",
    "projects": """Resume Optimizer Tool
• Built a FlashText-based skill extractor processing 1,000 resumes/minute
• Deployed on Streamlit Cloud with zero API costs

Portfolio Website
• Designed and built personal site using React and TypeScript
• Hosted on AWS with CloudFront CDN

Analytics Dashboard
• Created interactive dashboard with Plotly and Pandas

Crypto Tracker
• Real-time crypto price dashboard using WebSocket and Redis""",
    "certifications": """AWS Certified Solutions Architect
Google Cloud Professional Data Engineer
Kubernetes Administrator (CKA)
Docker Certified Associate""",
    "education": """B.Tech Computer Science | IIT Delhi
2018 | CGPA: 8.9/10""",
    "other": "",
}

SAMPLE_SCORE_DATA = {
    "ats_score": 78,
    "weighted_skill_score": 80,
    "tfidf_score": 60,
    "semantic_score": 70,
    "matched_keywords": ["python", "fastapi", "docker", "kubernetes", "aws", "postgresql", "redis", "react"],
    "missing_keywords": ["terraform", "kafka"],
    "matched_count": 8,
    "missing_count": 2,
    "total_keywords": 10,
}

SAMPLE_JD_KEYWORDS = {
    "must_have": ["python", "fastapi", "docker", "kubernetes", "aws"],
    "nice_to_have": ["postgresql", "redis", "react", "terraform", "kafka"],
    "job_title": "Senior Backend Engineer",
    "company": "CloudCo",
    "experience": "Senior",
}

SAMPLE_ARCHETYPE = {
    "display_name": "Backend Engineer",
    "role_label": "Backend / Server-Side Engineer",
    "skill_priority": ["python", "fastapi", "docker", "kubernetes", "aws", "postgresql", "redis"],
    "preferred_section_order": ["summary", "skills", "experience", "projects", "certifications", "education"],
    "summary_template": "Backend Engineer with {years_experience} of experience building scalable systems. Proficient in {top_3_skills}.",
}


# ---------------------------------------------------------------------------
# Import generator components
# ---------------------------------------------------------------------------
from utils.document_generator import (
    create_resume_docx,
    parse_experience_blocks,
    parse_project_blocks,
    rank_bullets_by_jd_overlap,
    assert_no_duplicate_sections,
    _trim_lowest_overlap_item,
    CONTENT_BUDGETS,
)


# ---------------------------------------------------------------------------
# Test 1: No duplicate name in generated document
# ---------------------------------------------------------------------------
print("\n=== 1: No duplicate name ===")

docx_bytes = create_resume_docx(
    resume_text=SAMPLE_RESUME_TEXT,
    job_keywords=SAMPLE_JD_KEYWORDS,
    score_data=SAMPLE_SCORE_DATA,
    archetype_data=SAMPLE_ARCHETYPE,
    sections=SAMPLE_SECTIONS,
    page_mode="2-page",
)
doc = Document(io.BytesIO(docx_bytes.read()))
texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

name_count = sum(1 for t in texts if "john smith" in t.lower())
check("Candidate name appears exactly once", name_count == 1, f"found {name_count}x")

# ---------------------------------------------------------------------------
# Test 2: Each section heading appears at most once
# ---------------------------------------------------------------------------
print("\n=== 2: Section headings appear at most once ===")

docx_bytes2 = create_resume_docx(
    resume_text=SAMPLE_RESUME_TEXT,
    job_keywords=SAMPLE_JD_KEYWORDS,
    score_data=SAMPLE_SCORE_DATA,
    archetype_data=SAMPLE_ARCHETYPE,
    sections=SAMPLE_SECTIONS,
    page_mode="2-page",
)
doc2 = Document(io.BytesIO(docx_bytes2.read()))
all_text = [p.text.strip().upper() for p in doc2.paragraphs if p.text.strip()]

for heading in ["PROFESSIONAL SUMMARY", "TECHNICAL SKILLS", "PROFESSIONAL EXPERIENCE",
                "PROJECTS", "CERTIFICATIONS", "EDUCATION"]:
    count = sum(1 for t in all_text if heading in t)
    check(f"'{heading}' appears <= 1 time", count <= 1, f"found {count}x")


# ---------------------------------------------------------------------------
# Test 3: Raw resume_text NOT dumped (verify absence of contact line duplication)
# ---------------------------------------------------------------------------
print("\n=== 3: No raw resume_text dump (no duplicated contact/skills block) ===")

skills_block_count = sum(1 for t in all_text if "TECHNICAL SKILLS" in t)
check("TECHNICAL SKILLS heading not duplicated", skills_block_count <= 1, f"found {skills_block_count}x")

summary_count = sum(1 for t in all_text if "PROFESSIONAL SUMMARY" in t)
check("PROFESSIONAL SUMMARY not duplicated", summary_count <= 1, f"found {summary_count}x")


# ---------------------------------------------------------------------------
# Test 4: 1-page budget caps correctly
# ---------------------------------------------------------------------------
print("\n=== 4: 1-page budget caps roles and projects ===")

docx_1pg = create_resume_docx(
    resume_text=SAMPLE_RESUME_TEXT,
    job_keywords=SAMPLE_JD_KEYWORDS,
    score_data=SAMPLE_SCORE_DATA,
    archetype_data=SAMPLE_ARCHETYPE,
    sections=SAMPLE_SECTIONS,
    page_mode="1-page",
)
doc_1pg = Document(io.BytesIO(docx_1pg.read()))
all_1pg = [p.text.strip() for p in doc_1pg.paragraphs if p.text.strip()]

# With 3 roles and 1-page budget (max_roles=2), the third role header should not appear
third_role_present = any("WebAgency" in t for t in all_1pg)
check("1-page: oldest role (WebAgency) excluded", not third_role_present, f"present={third_role_present}")

# 4th project should not appear in 1-page (max_projects=2)
crypto_present = any("Crypto" in t or "crypto" in t for t in all_1pg)
check("1-page: 4th project (Crypto Tracker) excluded", not crypto_present, f"present={crypto_present}")

# Only top 3 certs (max_certs=3)
docker_cert_present = any("Docker" in t and "Certified" in t for t in all_1pg)
check("1-page: 4th cert (Docker) excluded", not docker_cert_present, f"present={docker_cert_present}")


# ---------------------------------------------------------------------------
# Test 5: 2-page budget includes all roles and more projects
# ---------------------------------------------------------------------------
print("\n=== 5: 2-page budget includes all content ===")

docx_2pg = create_resume_docx(
    resume_text=SAMPLE_RESUME_TEXT,
    job_keywords=SAMPLE_JD_KEYWORDS,
    score_data=SAMPLE_SCORE_DATA,
    archetype_data=SAMPLE_ARCHETYPE,
    sections=SAMPLE_SECTIONS,
    page_mode="2-page",
)
doc_2pg = Document(io.BytesIO(docx_2pg.read()))
all_2pg = [p.text.strip() for p in doc_2pg.paragraphs if p.text.strip()]

third_role_2pg = any("WebAgency" in t for t in all_2pg)
check("2-page: all 3 roles included (WebAgency present)", third_role_2pg)

portfolio_present = any("Portfolio" in t for t in all_2pg)
check("2-page: 2nd project (Portfolio Website) present", portfolio_present)


# ---------------------------------------------------------------------------
# Test 6: Trim loop removes lowest-JD-overlap bullet, not highest
# ---------------------------------------------------------------------------
print("\n=== 6: Trim loop priority (lowest-overlap removed first) ===")

exp_blocks_test = [
    {
        "header": "Role A",
        "sub": "",
        "bullets": [
            "Deployed kubernetes cluster on AWS using Docker containers",   # high overlap
            "Organized team meetings and sent weekly email updates",           # low overlap (no JD skills)
        ],
    }
]
proj_blocks_test = []
jd_set = {"kubernetes", "aws", "docker", "python", "fastapi"}

# Rank bullets within block to simulate what _build_doc does
exp_blocks_test[0]["bullets"] = rank_bullets_by_jd_overlap(
    exp_blocks_test[0]["bullets"], jd_set
)

# The high-overlap bullet should be first after ranking
high_overlap_first = "kubernetes" in exp_blocks_test[0]["bullets"][0].lower()
check("High-overlap bullet ranked first", high_overlap_first,
      f"first={exp_blocks_test[0]['bullets'][0][:50]}")

# Trim: lowest overlap removed
trimmed = _trim_lowest_overlap_item(exp_blocks_test, proj_blocks_test, [], jd_set)
check("Trim removed one bullet", trimmed)

# The remaining bullet should be the high-overlap one
remaining_bullets = exp_blocks_test[0]["bullets"]
check("Remaining bullet is the JD-relevant one",
      len(remaining_bullets) == 1 and "kubernetes" in remaining_bullets[0].lower(),
      f"remaining={remaining_bullets}")


# ---------------------------------------------------------------------------
# Test 7: assert_no_duplicate_sections raises on real duplication
# ---------------------------------------------------------------------------
print("\n=== 7: Duplication assertion catches real duplicates ===")

dup_doc = Document()
dup_doc.add_paragraph("John Smith")   # name once
dup_doc.add_paragraph("PROFESSIONAL EXPERIENCE")
dup_doc.add_paragraph("PROFESSIONAL EXPERIENCE")  # duplicated!

try:
    assert_no_duplicate_sections(dup_doc, "John Smith")
    check("Duplication assertion fires on duplicate section", False, "Should have raised")
except AssertionError as e:
    check("Duplication assertion fires on duplicate section", True, str(e)[:60])

# Clean doc should pass
clean_doc = Document()
clean_doc.add_paragraph("John Smith")
clean_doc.add_paragraph("PROFESSIONAL EXPERIENCE")
clean_doc.add_paragraph("EDUCATION")
try:
    assert_no_duplicate_sections(clean_doc, "John Smith")
    check("Clean document passes duplication assertion", True)
except AssertionError as e:
    check("Clean document passes duplication assertion", False, str(e))


# ---------------------------------------------------------------------------
# Test 8: parse_experience_blocks correctly segments roles
# ---------------------------------------------------------------------------
print("\n=== 8: parse_experience_blocks ===")

blocks = parse_experience_blocks(SAMPLE_SECTIONS["experience"])
check("Three roles parsed", len(blocks) == 3, f"got {len(blocks)}")
check("First role is TechCorp", "TechCorp" in blocks[0]["header"], f"header={blocks[0]['header']}")
check("First role has 4 bullets", len(blocks[0]["bullets"]) == 4, f"got {len(blocks[0]['bullets'])}")


# ---------------------------------------------------------------------------
# Test 9: parse_project_blocks correctly segments projects
# ---------------------------------------------------------------------------
print("\n=== 9: parse_project_blocks ===")

proj = parse_project_blocks(SAMPLE_SECTIONS["projects"])
check("Four projects parsed", len(proj) == 4, f"got {len(proj)}")
check("First project has 2 bullets", len(proj[0]["bullets"]) == 2, f"got {len(proj[0]['bullets'])}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 65)
passed = sum(1 for r in results if r[0] == PASS)
print(f"Results: {passed}/{len(results)} tests passed")
if passed == len(results):
    print("ALL duplication + page-length tests PASSED")
else:
    for r in results:
        if r[0] == FAIL:
            print(f"  FAILED: {r[1]}  {r[2]}")
print("=" * 65)
