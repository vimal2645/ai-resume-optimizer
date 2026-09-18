"""
core/role_detector.py
=====================
Detects the target job role from a JD using keyword-cluster overlap scoring.
Zero external API calls — pure string matching against role_archetypes.json.
"""

import re
import json
import os
from core.parser import extract_skills_from_text

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Minimum keyword-hit count for a role to be selected (else → generic)
MIN_ARCHETYPE_THRESHOLD = 4
MIN_ARCHETYPE_MARGIN = 2


def _load_archetypes() -> dict:
    path = os.path.join(_BASE, "data", "role_archetypes.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_synonym_map() -> dict:
    path = os.path.join(_BASE, "data", "synonym_map.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalise(text: str, synonym_map: dict) -> str:
    """Apply synonym substitution and lowercase."""
    text_lower = text.lower()
    for alias, canonical in synonym_map.items():
        pattern = r'(?<!\w)' + re.escape(alias) + r'(?!\w)'
        text_lower = re.sub(pattern, canonical, text_lower)
    return text_lower


def _keyword_present(text: str, keyword: str) -> bool:
    """Match normal text and space-less concatenated skill tags."""
    keyword_lower = keyword.lower()
    if re.search(r"(?<!\w)" + re.escape(keyword_lower) + r"(?!\w)", text):
        return True
    compact_text = re.sub(r"[^a-z0-9]+", "", text)
    compact_keyword = re.sub(r"[^a-z0-9]+", "", keyword_lower)
    return len(compact_keyword) >= 4 and compact_keyword in compact_text


def detect_role(jd_text: str, archetypes: dict = None, synonym_map: dict = None) -> dict:
    """
    Score the JD against every archetype by counting how many signal keywords
    appear in the normalised JD text.

    Returns:
        archetype_name  – string key into archetypes dict
        confidence      – int hit count of winning archetype
        archetype_data  – full archetype definition dict
        scores          – dict {archetype_name: hit_count} for all archetypes
    """
    if archetypes is None:
        archetypes = _load_archetypes()
    if synonym_map is None:
        synonym_map = _load_synonym_map()

    normalised_jd = _normalise(jd_text, synonym_map)
    extracted_skills = set(extract_skills_from_text(jd_text, allow_concatenated=True))
    extracted_compact = {
        re.sub(r"[^a-z0-9]+", "", skill.lower()) for skill in extracted_skills
    }

    scores: dict = {}
    for name, data in archetypes.items():
        if name == "generic":
            continue  # Skip generic from competition
        hit_count = 0
        for keyword in data.get("signal_keywords", []):
            # Check for whole-word-ish presence (allow partial for compound terms)
            keyword_compact = re.sub(r"[^a-z0-9]+", "", keyword.lower())
            if keyword.lower() in extracted_skills or keyword_compact in extracted_compact or _keyword_present(normalised_jd, keyword):
                hit_count += 1
        for title_keyword in data.get("title_keywords", []):
            if _keyword_present(normalised_jd, title_keyword):
                hit_count += 8
        scores[name] = hit_count

    if not scores:
        best_role = "generic"
        best_score = 0
    else:
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best_role = ranked[0][0]
        best_score = scores[best_role]
        second_score = ranked[1][1] if len(ranked) > 1 else 0
        if best_score < MIN_ARCHETYPE_THRESHOLD or best_score - second_score < MIN_ARCHETYPE_MARGIN:
            best_role = "generic"

    # Fall back to generic if no archetype passes threshold
    if best_score < MIN_ARCHETYPE_THRESHOLD:
        best_role = "generic"

    archetype_data = archetypes.get(best_role, archetypes.get("generic", {}))

    return {
        "archetype_name": best_role,
        "confidence": best_score if best_role != "generic" else 0,
        "archetype_data": archetype_data,
        "scores": scores,
    }





def extract_top_skills(skills: list, archetype_data: dict, n: int = 3) -> list:
    """
    Return the top-n skills from the candidate's skill list, ordered by the
    role's priority weighting. Skills not in the priority list go last.
    """
    priority = [s.lower() for s in archetype_data.get("skill_priority", [])]
    priority_index = {s: i for i, s in enumerate(priority)}

    def rank(skill):
        return priority_index.get(skill.lower(), len(priority))

    sorted_skills = sorted(skills, key=rank)
    return sorted_skills[:n]
