"""
core/parser.py
==============
Resume and job-description parsing.  Zero external API calls.

Resume path:
  1. Binary extraction via pypdf (PDF) or python-docx (DOCX)
  2. Extraction-quality check (format warning for garbled/too-short text)
  3. Section segmentation via regex
  4. Synonym normalisation
  5. FlashText skill extraction run across the ENTIRE resume text
     (skills_full) AND separately across only the Skills section text
     (skills_in_skills_section) — this supports three-bucket classification.

JD path:
  1. Plain text in -> synonym normalisation -> FlashText skill extraction
  2. Regex extraction of job_title, company, experience_level
  (No LLM anywhere in this file.)

Three-bucket classification (classify_skills):
  ALREADY_LISTED   — in JD AND in the resume's Skills section
  OPTIMIZABLE      — in JD AND found elsewhere in resume (exp/projects/summary)
                     but NOT explicitly in the Skills section — safe to add
  GENUINELY_MISSING — NOT found anywhere in the resume's full text — NEVER
                     written to any output document
"""

import re
import io
import json
import math
import os
import streamlit as st

# ---------------------------------------------------------------------------
# Helpers — load data files once at module level
# ---------------------------------------------------------------------------
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_json(relative_path: str):
    full = os.path.join(_BASE, relative_path)
    with open(full, "r", encoding="utf-8") as f:
        return json.load(f)


# These are loaded once on first import (no Streamlit cache needed here —
# the @st.cache_resource lives in the matcher module that builds FlashText)
try:
    SKILLS_DB: list = _load_json("data/skills_db.json")
    SYNONYM_MAP: dict = _load_json("data/synonym_map.json")
except FileNotFoundError as e:
    SKILLS_DB = []
    SYNONYM_MAP = {}
    import warnings
    warnings.warn(f"Data file not found: {e}. Skill extraction will be limited.")


# ---------------------------------------------------------------------------
# Section header patterns (case-insensitive)
# ---------------------------------------------------------------------------
_SECTION_PATTERNS = {
    "summary": re.compile(
        r"^(summary|objective|profile|about me|professional summary|career objective)\s*:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "experience": re.compile(
        r"^(experience|work experience|professional experience|employment|work history|career history)\s*:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "skills": re.compile(
        r"^(skills|technical\s+skills?|core\s+competencies|competencies|"
        r"technologies|expertise|key\s+skills?|relevant\s+skills?|"
        r"technical\s+proficiencies|areas\s+of\s+expertise|"
        r"professional\s+skills?|hard\s+skills?|software\s+skills?|"
        r"programming\s+skills?)\s*:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "education": re.compile(
        r"^(education|educational background|academic background|qualifications|academics)\s*:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "projects": re.compile(
        r"^(projects|personal projects|key projects|side projects|open source|portfolio)\s*:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "certifications": re.compile(
        r"^(certifications|certificates|credentials|licenses|courses|training)\s*:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "achievements": re.compile(
        r"^(achievements|accomplishments|awards|honors)\s*:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
}

# Sections from which skills should be extracted for the LEGACY path
SKILL_SECTIONS = {"skills", "experience", "projects", "certifications", "achievements"}


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF using pypdf (replaces PyPDF2)."""
    try:
        from pypdf import PdfReader
        pdf_file = io.BytesIO(file_bytes)
        reader = PdfReader(pdf_file)
        pages = []
        for page in reader.pages:
            txt = page.extract_text()
            if txt:
                pages.append(txt)
        return "\n".join(pages).strip()
    except Exception:
        return ""


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from DOCX using python-docx."""
    try:
        import docx
        doc_file = io.BytesIO(file_bytes)
        doc = docx.Document(doc_file)
        parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                parts.append(para.text)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        parts.append(cell.text)
        return "\n".join(parts).strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Extraction quality check
# ---------------------------------------------------------------------------

def _char_entropy(text: str) -> float:
    """Shannon entropy of character distribution (bits per character)."""
    if not text:
        return 0.0
    freq = {}
    for c in text:
        freq[c] = freq.get(c, 0) + 1
    n = len(text)
    return -sum((v / n) * math.log2(v / n) for v in freq.values())


def check_extraction_quality(text: str) -> dict:
    """
    Return a dict:
      ok        – bool, True if text looks usable
      warning   – human-readable warning string (empty if ok)
    Heuristics:
      - Less than 200 meaningful characters → likely garbled
      - Entropy < 3.0 bits/char → likely repeated junk / encoding artefacts
      - Ratio of alphabetic chars < 0.40 → likely OCR/table corruption
    """
    clean = text.strip()
    if not clean:
        return {"ok": False, "warning": "⚠️ No text could be extracted from your resume. The file may be image-based, scanned, or password-protected. Please upload a text-selectable PDF or DOCX."}

    alpha = sum(c.isalpha() for c in clean)
    alpha_ratio = alpha / max(len(clean), 1)
    entropy = _char_entropy(clean)

    if len(clean) < 200:
        return {"ok": False, "warning": f"⚠️ Only {len(clean)} characters were extracted — your file appears to use complex tables, multi-column layouts, or embedded images. ATS scoring may be inaccurate. Consider converting your resume to a single-column, text-based format."}

    if entropy < 3.0:
        return {"ok": False, "warning": "⚠️ The extracted text appears garbled or contains mostly special characters. This often happens with scanned PDFs or heavily formatted files. ATS scoring may be unreliable."}

    if alpha_ratio < 0.40:
        return {"ok": False, "warning": "⚠️ Less than 40 % of the extracted content is readable text. Your resume likely uses heavy formatting (tables, text boxes, or images). Consider using a plain single-column layout for best ATS results."}

    return {"ok": True, "warning": ""}


# ---------------------------------------------------------------------------
# Synonym normalisation
# ---------------------------------------------------------------------------

def apply_synonyms(text: str, synonym_map: dict = None) -> str:
    """
    Replace known abbreviations / aliases with canonical skill names.
    Operates on whole-word boundaries to avoid false replacements.
    """
    if synonym_map is None:
        synonym_map = SYNONYM_MAP

    text_lower = text.lower()
    for alias, canonical in synonym_map.items():
        # Use word-boundary aware replacement (alias may be multi-word)
        pattern = r'(?<!\w)' + re.escape(alias) + r'(?!\w)'
        text_lower = re.sub(pattern, canonical, text_lower, flags=re.IGNORECASE)
    return text_lower


# ---------------------------------------------------------------------------
# Section segmentation
# ---------------------------------------------------------------------------

def segment_resume_text(text: str) -> dict:
    """
    Split resume text into labelled sections using regex header detection.
    Returns a dict keyed by section name, values are the section body text.
    An 'other' key collects lines that don't fall under any detected section.
    """
    lines = text.split("\n")
    sections: dict = {k: [] for k in _SECTION_PATTERNS}
    sections["other"] = []
    current_section = "other"

    for line in lines:
        stripped = line.strip()
        matched_section = None
        for section_name, pattern in _SECTION_PATTERNS.items():
            if pattern.match(stripped):
                matched_section = section_name
                break
        if matched_section:
            current_section = matched_section
        else:
            sections[current_section].append(line)

    # Join each section's lines into a single string
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def get_skill_text(sections: dict) -> str:
    """Return concatenated text from skill-relevant sections only."""
    parts = []
    for section_name in SKILL_SECTIONS:
        body = sections.get(section_name, "")
        if body:
            parts.append(body)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Skill extraction  (FlashText based, cached at app level)
# ---------------------------------------------------------------------------

COMMON_WORDS_BLOCKLIST = {
    "make", "build", "do", "let's", "can", "will", "framework",
    "tool", "system", "software", "product", "design", "test",
    "support", "create", "manage", "lead", "develop", "code",
    "drive", "plan", "time", "work", "use", "help", "need",
    "innovation", "innovative", "optimization", "optimize", "improvement",
    "quality", "solutions", "solution", "results", "business", "team",
}

def extract_skills_from_text(text: str, keyword_processor=None, allow_concatenated: bool = False) -> list:
    """
    Extract skills using a pre-built FlashText KeywordProcessor.
    Falls back to substring match against SKILLS_DB if no processor provided.
    """
    normalised = apply_synonyms(text)

    found = set()
    if keyword_processor is not None:
        found.update(keyword_processor.extract_keywords(normalised))

    # Scan compact vocabulary only in explicit run-on skill contexts. A
    # global substring scan would turn "electron" or "go" inside unrelated
    # prose into false required skills.
    text_lower = normalised.lower()
    compact_sources = []
    if allow_concatenated:
        for line in text_lower.splitlines() or [text_lower]:
            is_key_skill_line = bool(re.search(
                r"\b(key skills?|technical skills?|technologies|requirements?)\b",
                line,
            ))
            non_space_chars = len(re.sub(r"\s+", "", line))
            few_spaces = len(re.findall(r"\s", line)) <= 2
            if is_key_skill_line or (non_space_chars >= 30 and few_spaces):
                compact_sources.append(re.sub(r"[^a-z0-9]+", "", line))
    for skill in SKILLS_DB:
        skill_lower = skill.lower()
        if skill_lower in COMMON_WORDS_BLOCKLIST:
            continue
        boundary_match = re.search(r'(?<!\w)' + re.escape(skill_lower) + r'(?!\w)', text_lower)
        compact_skill = re.sub(r"[^a-z0-9]+", "", skill_lower)
        concatenated_match = any(
            len(compact_skill) >= 4 and compact_skill in source
            for source in compact_sources
        )
        if boundary_match or concatenated_match:
            found.add(skill)

    filtered = {skill for skill in found if skill.lower() not in COMMON_WORDS_BLOCKLIST}
    # A substring scan can find "java" inside "javascript". Keep the
    # longest curated match when the shorter term has no standalone boundary.
    for skill in list(filtered):
        skill_lower = skill.lower()
        if len(skill_lower) < 5:
            standalone = re.search(r'(?<!\w)' + re.escape(skill_lower) + r'(?!\w)', text_lower)
            contained_in_longer = any(
                skill != other and skill_lower in other.lower() and len(other) > len(skill)
                for other in filtered
            )
            if not standalone and contained_in_longer:
                filtered.remove(skill)
    return sorted(filtered)


# ---------------------------------------------------------------------------
# Three-bucket skill classification
# ---------------------------------------------------------------------------

def classify_skills(
    jd_skills: list,
    skills_full: list,
    skills_in_skills_section: list,
    synonym_map: dict = None,
) -> dict:
    """
    Classify each JD skill into exactly one of three buckets.

    Parameters
    ----------
    jd_skills               : all skills found in the job description
    skills_full             : skills extracted from the ENTIRE resume text
    skills_in_skills_section: skills extracted from the Skills section only
    synonym_map             : synonym map for canonicalization

    Returns
    -------
    {
        "already_listed":    list,  # in JD + already in Skills section
        "optimizable":       list,  # in JD + found elsewhere in resume
        "genuinely_missing": list,  # in JD + NOT found anywhere in resume
    }

    GENUINELY_MISSING skills must NEVER be written to any output document.
    """
    if synonym_map is None:
        synonym_map = SYNONYM_MAP

    def canon(s: str) -> str:
        return apply_synonyms(s, synonym_map).lower().strip()

    full_canon = {canon(s) for s in skills_full}
    listed_canon = {canon(s) for s in skills_in_skills_section}

    already_listed = []
    optimizable = []
    genuinely_missing = []

    for skill in jd_skills:
        c = canon(skill)
        if c in listed_canon:
            already_listed.append(skill)
        elif c in full_canon:
            optimizable.append(skill)
        else:
            genuinely_missing.append(skill)

    return {
        "already_listed": already_listed,
        "optimizable": optimizable,
        "genuinely_missing": genuinely_missing,
    }


# ---------------------------------------------------------------------------
# Skills-section text extraction (heading-alias aware)
# ---------------------------------------------------------------------------

# All heading aliases that mean "this is the skills section".
# Extend this list to add future variants without touching any regex.
_SKILLS_HEADING_ALIASES = [
    "technical skills",
    "skills",
    "relevant skills",
    "core competencies",
    "competencies",
    "technologies",
    "expertise",
    "key skills",
    "technical proficiencies",
    "areas of expertise",
    "professional skills",
    "hard skills",
    "software skills",
    "programming skills",
]

# Pre-compiled set of normalised alias strings for O(1) lookup
_SKILLS_HEADING_ALIAS_SET = {h.lower() for h in _SKILLS_HEADING_ALIASES}

# Pattern that matches any alias as a standalone line (with optional colon)
_SKILLS_HEADING_RE = re.compile(
    r"^\s*(?:[^\w\s]*\s*)?(" + "|".join(re.escape(a) for a in _SKILLS_HEADING_ALIASES) + r")\b.*$",
    re.IGNORECASE,
)

# All non-skills section headings (to know when the skills section ends)
_OTHER_SECTION_HEADING_RE = re.compile(
    r"^(summary|objective|profile|about me|professional summary|career objective|"
    r"experience|work experience|professional experience|employment|work history|career history|"
    r"education|educational background|academic background|qualifications|academics|"
    r"projects|personal projects|key projects|side projects|open source|portfolio|"
    r"certifications|certificates|credentials|licenses|courses|training|"
    r"achievements|accomplishments|awards|honors)\s*:?\s*$",
    re.IGNORECASE,
)


def _extract_skills_section_text(
    full_text: str,
    sections: dict,
) -> tuple:
    """
    Return (skills_text, heading_found, heading_label).

    Strategy (in order of preference):
    1. If the segmenter already captured a 'skills' section, use it directly.
    2. If the segmenter missed it (non-standard heading), scan raw text
       line-by-line for any alias in _SKILLS_HEADING_ALIASES.  Collect lines
       until the next recognised (non-skills) section heading or end of text.
    3. If no heading found at all, return ("", False, "").
    """
    # ── Priority 1: segmenter already found it ─────────────────────────────
    segmented = sections.get("skills", "").strip()
    if segmented:
        return segmented, True, "skills"

    # ── Priority 2: raw line scan for all heading aliases ──────────────────
    lines = full_text.split("\n")
    inside_skills = False
    heading_label = ""
    collected: list = []

    for line in lines:
        stripped = line.strip()
        stripped_lower = stripped.lower().rstrip(":").strip()

        if not inside_skills:
            if _SKILLS_HEADING_RE.match(stripped):
                inside_skills = True
                heading_label = stripped
                continue  # don't include the heading itself in the content
        else:
            # Stop at the next recognised non-skills section heading
            if stripped and _OTHER_SECTION_HEADING_RE.match(stripped):
                break
            # Also stop at another skills-alias heading (shouldn't happen,
            # but guards against infinite loops in malformed text)
            if stripped and _SKILLS_HEADING_RE.match(stripped):
                break
            collected.append(line)

    if inside_skills and collected:
        return "\n".join(collected).strip(), True, heading_label

    # ── Priority 3: no heading found ───────────────────────────────────────
    return "", False, ""


# ---------------------------------------------------------------------------
# Public API — resume parsing
# ---------------------------------------------------------------------------

def parse_resume(file_bytes: bytes, filename: str, keyword_processor=None) -> dict:
    """
    Parse an uploaded resume file.

    Returns:
        text                    – raw extracted text
        sections                – dict of segmented sections
        skills_full             – skills from the ENTIRE resume text
        skills_in_skills_section– skills from the Skills section only
        skills                  – alias for skills_full (backward compat)
        quality                 – dict {ok, warning} from extraction quality check
    """
    filename_lower = filename.lower()
    if filename_lower.endswith(".pdf"):
        text = extract_text_from_pdf(file_bytes)
    elif filename_lower.endswith(".docx"):
        text = extract_text_from_docx(file_bytes)
    else:
        return {
            "text": "",
            "sections": {},
            "skills_full": [],
            "skills_in_skills_section": [],
            "skills": [],
            "quality": {"ok": False, "warning": "⚠️ Unsupported file format. Please upload a PDF or DOCX."},
        }

    quality = check_extraction_quality(text)

    # Segment regardless — partial sections are better than nothing
    sections = segment_resume_text(text)

    # --- Full-resume skill extraction (the candidate's TRUE skill universe) ---
    # Run FlashText across ALL text: Summary + Experience + Projects + Skills
    skills_full = extract_skills_from_text(text, keyword_processor)

    # --- Skills-section-only extraction with heading-aware fallback scan ---
    skills_section_text, skills_heading_found, skills_heading_label = \
        _extract_skills_section_text(text, sections)

    if skills_section_text.strip():
        skills_in_skills_section = extract_skills_from_text(
            skills_section_text, keyword_processor
        )
    else:
        skills_in_skills_section = []

    # Build warning if no skills heading was detected
    skills_section_warning = ""
    if not skills_heading_found:
        skills_section_warning = (
            "⚠\ufe0f Couldn't identify a Skills section heading in your resume. "
            "Skill classification may be incomplete — ensure your resume has a heading "
            "such as 'Technical Skills', 'Relevant Skills', 'Core Competencies', or similar."
        )

    return {
        "text": text,
        "sections": sections,
        "skills_full": skills_full,
        "skills_in_skills_section": skills_in_skills_section,
        "skills": skills_full,          # backward-compat alias
        "quality": quality,
        "skills_heading_found": skills_heading_found,
        "skills_heading_label": skills_heading_label,
        "skills_section_warning": skills_section_warning,
    }


# ---------------------------------------------------------------------------
# Public API — JD parsing (no LLM, pure regex + FlashText)
# ---------------------------------------------------------------------------

def parse_job_description(job_text: str, keyword_processor=None) -> dict:
    """
    Parse a raw job description string into structured data.
    No external API calls.

    Returns:
        must_have       – list of required skills
        nice_to_have    – list of nice-to-have skills (currently same source)
        job_title       – extracted or guessed job title string
        company         – extracted or guessed company name
        experience      – "Entry" | "Mid" | "Senior"
        raw_skills      – full list of all skills found in JD
    """
    # Normalise
    normalised_jd = apply_synonyms(job_text)

    # Extract all skills from the JD
    raw_skills = extract_skills_from_text(
        normalised_jd,
        keyword_processor,
        allow_concatenated=True,
    )

    # Heuristic split: first ⅔ of skills are "must-have" (appear earlier in text)
    split_idx = max(1, len(raw_skills) // 3 * 2)
    must_have = raw_skills[:split_idx]
    nice_to_have = raw_skills[split_idx:]

    # --- Extract job_title via regex ---
    title_patterns = [
        r'(?:job title|position|role|title)\s*[:\-–]\s*([A-Za-z][A-Za-z\s/&,\-]+)',
        r'(?:we are looking for|seeking|hiring)\s+(?:a|an)\s+([A-Za-z][A-Za-z\s/&,\-]+)',
        r'(?:^|\n)([A-Z][A-Za-z\s/&\-]{3,40})\s*\n',   # Capitalised heading at line start
    ]
    job_title = "Technical Position"
    for pat in title_patterns:
        m = re.search(pat, job_text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip().rstrip(".,;:")
            if 3 <= len(candidate) <= 60:
                job_title = candidate
                break

    # --- Extract company via regex ---
    company_patterns = [
        r'(?:company|employer|organisation|organization|at)\s*[:\-–]\s*([A-Za-z][A-Za-z0-9\s&,\.\-]+)',
        r'(?:join|joining)\s+([A-Z][A-Za-z0-9\s&,\.\-]{2,40})',
    ]
    company = "Company"
    for pat in company_patterns:
        m = re.search(pat, job_text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip().rstrip(".,;:")
            if 2 <= len(candidate) <= 60:
                company = candidate
                break

    # --- Experience level ---
    experience = "Mid"
    jd_lower = job_text.lower()
    if any(w in jd_lower for w in ["senior", "lead", "principal", "staff", "7+ year", "8+ year", "10+ year"]):
        experience = "Senior"
    elif any(w in jd_lower for w in ["junior", "entry", "fresher", "graduate", "intern", "0-2 year", "1-2 year"]):
        experience = "Entry"

    return {
        "must_have": must_have,
        "nice_to_have": nice_to_have,
        "job_title": job_title,
        "company": company,
        "experience": experience,
        "raw_skills": raw_skills,
    }
