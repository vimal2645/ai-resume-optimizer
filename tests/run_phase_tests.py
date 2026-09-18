import sys, io, os
sys.path.insert(0, '.')
from utils.document_generator import create_resume_docx
from core.parser import extract_skills_from_text, parse_job_description, apply_synonyms

def test_phase0_exception():
    try:
        # Force an error by passing a bad archetype_data dict that missing get
        create_resume_docx('text', {}, {}, archetype_data=[1], page_mode='1-page')
        print('Phase 0 Failed: No exception raised')
    except Exception as e:
        if 'object has no attribute' in str(e) or 'list indices must be integers' in str(e) or 'list' in str(e):
            print('Phase 0 Passed: Exception correctly propagated')
        else:
            print('Phase 0 Failed with wrong exception:', e)

test_phase0_exception()

def test_phase1_invariant():
    try:
        docx = create_resume_docx(
            resume_text='John Smith\njohn@example.com\nExperience\nPython developer',
            job_keywords={'must_have': ['python']},
            score_data={'matched_keywords': ['python'], 'ats_score': 100},
            archetype_data={'display_name': 'Backend', 'skill_priority': ['python']},
            page_mode='1-page',
            resume_skills=['python', 'numpy', 'css3']
        )
        print('Phase 1 Passed: Invariant did not crash on non-JD skills')
    except RuntimeError as e:
        print('Phase 1 Failed: Invariant crashed!', e)

test_phase1_invariant()

def test_phase7_junk_skills():
    text = "make build let's framework time"
    skills = extract_skills_from_text(text)
    if not skills:
        print('Phase 7 Passed: No junk skills extracted')
    else:
        print('Phase 7 Failed: Junk skills extracted:', skills)

test_phase7_junk_skills()

def test_phase8_soft_skills():
    from utils.ai_skill_matcher import AISkillMatcher
    matcher = AISkillMatcher()
    res = matcher.calculate_enhanced_ats_score(
        resume_skills=['python'],
        job_keywords={'must_have': ['collaboration', 'python']},
        resume_text='worked closely with stakeholders'
    )
    if 'collaboration' in res['matched_keywords'] and 'collaboration' not in res['missing_keywords']:
        print('Phase 8 Passed: Soft skill alias matched correctly')
    else:
        print('Phase 8 Failed: Soft skill alias did not match', res)

test_phase8_soft_skills()
