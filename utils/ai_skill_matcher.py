"""
utils/ai_skill_matcher.py
=========================
Weighted ATS scoring engine — zero external API calls, zero torch/transformers.

Two-tier composite score:
  a) Weighted skill match   (rapidfuzz token_set_ratio, role-priority weighted)
  b) TF-IDF cosine          (scikit-learn, fast CPU computation)

Composite: 0.60 * weighted_skill + 0.40 * tfidf
"""

import streamlit as st
from rapidfuzz import fuzz


# ---------------------------------------------------------------------------
# Cached model loaders (loaded once per Streamlit session)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Building skill index…")
def _load_keyword_processor():
    """Build FlashText KeywordProcessor from skills_db.json — cached."""
    import json
    import os
    from flashtext import KeywordProcessor

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skills_path = os.path.join(base, "data", "skills_db.json")
    with open(skills_path, "r", encoding="utf-8") as f:
        skills = json.load(f)

    kp = KeywordProcessor(case_sensitive=False)
    for skill in skills:
        kp.add_keyword(skill.lower())
    return kp


# ---------------------------------------------------------------------------
# Skill-level fuzzy matching (rapidfuzz)
# ---------------------------------------------------------------------------

_FUZZY_THRESHOLD = 80  # Slightly higher than thefuzz default for precision


def _fuzzy_match(job_skill: str, resume_skills: list) -> bool:
    """Return True if any resume skill fuzzy-matches the given job skill."""
    job_lower = job_skill.lower().strip()
    for rs in resume_skills:
        if fuzz.token_set_ratio(job_lower, rs.lower().strip()) >= _FUZZY_THRESHOLD:
            return True
    return False


SOFT_SKILL_ALIASES = {
    "collaboration": [
        "worked closely with", "cross-functional", "partnered with", "collaborated",
        "collaborative", "teamwork", "stakeholder collaboration", "in partnership with",
    ],
    "communication": [
        "presented findings", "written documentation", "explained to stakeholders",
        "communicated", "presentation", "presented to", "documented", "liaised with",
    ],
    "leadership": [
        "led a team", "mentored", "coached", "owned the project", "leadership",
        "managed", "supervised", "guided", "drove the initiative",
    ],
    "problem solving": [
        "diagnosed", "root cause", "resolved", "troubleshoot", "problem-solving",
        "debugged", "investigated and fixed", "identified and resolved",
    ],
}


# ---------------------------------------------------------------------------
# TF-IDF cosine similarity
# ---------------------------------------------------------------------------

def _tfidf_similarity(text_a: str, text_b: str) -> float:
    """Compute TF-IDF cosine similarity between two documents [0, 1]."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        if not text_a.strip() or not text_b.strip():
            return 0.0

        vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
        matrix = vectorizer.fit_transform([text_a, text_b])
        score = float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
        return max(0.0, min(1.0, score))
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

class AISkillMatcher:

    def calculate_enhanced_ats_score(
        self,
        resume_skills: list,
        job_keywords: dict,
        archetype_data: dict = None,
        resume_text: str = "",
        jd_text: str = "",
    ) -> dict:
        """
        Compute a composite ATS score.

        Parameters
        ----------
        resume_skills   : list of skills extracted from the FULL resume text
        job_keywords    : dict with keys 'must_have', 'nice_to_have'
        archetype_data  : role archetype definition (for priority weighting)
        resume_text     : full resume text (for TF-IDF)
        jd_text         : full JD text (for TF-IDF)

        Returns
        -------
        dict with keys: ats_score, weighted_skill_score, tfidf_score,
                        matched_keywords, missing_keywords,
                        matched_count, missing_count, total_keywords
        """
        must_have = list(job_keywords.get("must_have") or [])
        nice_to_have = list(job_keywords.get("nice_to_have") or [])
        all_jd_skills = list(dict.fromkeys(must_have + nice_to_have))  # dedupe, preserve order

        # Build priority weight map from archetype
        priority_list = []
        if archetype_data:
            priority_list = [s.lower() for s in archetype_data.get("skill_priority", [])]
        priority_index = {s: i for i, s in enumerate(priority_list)}

        matched_keywords = []
        missing_keywords = []
        weighted_matched = 0.0
        total_weight = 0.0

        for skill in all_jd_skills:
            # Weight: skills earlier in priority list are worth more
            rank = priority_index.get(skill.lower(), len(priority_list))
            # Linear decay: top skill = weight 1.0, last = 0.1
            max_rank = max(len(priority_list), 1)
            weight = max(0.1, 1.0 - (rank / max_rank) * 0.9)
            total_weight += weight

            is_matched = _fuzzy_match(skill, resume_skills)

            # Soft skills phrase matching fallback
            if not is_matched and resume_text:
                skill_lower = skill.lower().strip()
                if skill_lower in SOFT_SKILL_ALIASES:
                    resume_text_lower = resume_text.lower()
                    for alias in SOFT_SKILL_ALIASES[skill_lower]:
                        if alias in resume_text_lower:
                            is_matched = True
                            break

            if is_matched:
                matched_keywords.append(skill)
                weighted_matched += weight
            else:
                missing_keywords.append(skill)

        # Weighted skill score [0, 100]
        weighted_skill_score = int((weighted_matched / max(total_weight, 1e-9)) * 100)

        # TF-IDF score [0, 100]
        tfidf_raw = _tfidf_similarity(resume_text, jd_text) if (resume_text and jd_text) else 0.0
        tfidf_score = int(tfidf_raw * 100)

        # Composite score: 60% skill match + 40% TF-IDF (no semantic model)
        composite = 0.60 * weighted_skill_score + 0.40 * tfidf_score
        ats_score = max(0, min(100, int(composite)))

        return {
            "ats_score": ats_score,
            "weighted_skill_score": weighted_skill_score,
            "tfidf_score": tfidf_score,
            "matched_keywords": matched_keywords,
            "missing_keywords": missing_keywords,
            "matched_count": len(matched_keywords),
            "missing_count": len(missing_keywords),
            "total_keywords": len(all_jd_skills),
        }

    # Keep backward-compatible thin wrapper used in older code paths
    def intelligent_match(self, job_skill: str, resume_skills: list, threshold: int = 80) -> bool:
        return _fuzzy_match(job_skill, resume_skills)


# Module-level singleton (preserves old import style: `from utils.ai_skill_matcher import ai_matcher`)
ai_matcher = AISkillMatcher()
