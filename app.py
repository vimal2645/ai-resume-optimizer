"""
app.py — AI Resume Optimizer (In-Place Edit Edition)
=====================================================
Streamlit frontend — zero external API calls, zero torch/transformers.

Pipeline:
  1. pypdf / python-docx      → raw text extraction
  2. core/parser.py           → section segmentation + full-resume skill
                                extraction (FlashText across ALL sections)
  3. core/parser.classify_skills() → three-bucket classification:
                                     ALREADY_LISTED / OPTIMIZABLE / GENUINELY_MISSING
  4. utils/ai_skill_matcher.py → composite ATS score (0.6 skill + 0.4 TF-IDF)
  5. utils/inplace_editor.py  → append OPTIMIZABLE skills to the Skills
                                section of the ORIGINAL file (format-matched)
  6. utils/document_generator.py → cover letter + ATS report DOCX
"""

import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Resume Optimizer",
    page_icon="🎯",
    layout="wide",
    menu_items={"About": "LLM-Free ATS Resume Optimizer — 100% local, zero API costs."},
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');

    * { font-family: 'Poppins', sans-serif; }

    .stApp {
        background: linear-gradient(-45deg, #ee7752, #e73c7e, #23a6d5, #23d5ab);
        background-size: 400% 400%;
        animation: gradientShift 15s ease infinite;
    }
    @keyframes gradientShift {
        0%   { background-position: 0% 50%; }
        50%  { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    .main .block-container { padding: 2rem 1rem; max-width: 1400px; }

    .main-header {
        font-size: 3rem; font-weight: 700; text-align: center;
        background: linear-gradient(45deg, #ff6ec4, #7873f5, #4facfe, #00f2fe);
        background-size: 300% 300%;
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        animation: colorShift 8s ease infinite; margin-bottom: 0.5rem;
    }
    @keyframes colorShift {
        0%   { background-position: 0% 50%; }
        50%  { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    .metric-card {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        background-size: 200% 200%; animation: cardGlow 4s ease infinite;
        padding: 1.5rem; border-radius: 15px; color: white; text-align: center;
        box-shadow: 0 10px 30px rgba(0,0,0,0.3); transition: all 0.3s ease;
    }
    @keyframes cardGlow {
        0%, 100% { background-position: 0% 50%; }
        50%       { background-position: 100% 50%; }
    }
    .metric-card:hover { transform: scale(1.08) rotate(2deg); box-shadow: 0 15px 40px rgba(0,0,0,0.4); }
    .metric-card h2 { font-size: 2.5rem; margin: 0; font-weight: 700; text-shadow: 2px 2px 8px rgba(0,0,0,0.3); }

    .role-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.2rem; border-radius: 12px; color: white; text-align: center;
        box-shadow: 0 8px 25px rgba(102,126,234,0.4); transition: all 0.3s ease;
    }
    .role-card:hover { transform: translateY(-3px); box-shadow: 0 12px 35px rgba(102,126,234,0.6); }
    .role-card h3 { margin: 0; font-size: 1.1rem; }

    /* Skill badge styles — three buckets */
    .skill-listed {
        background: linear-gradient(135deg, #11998e, #38ef7d, #06beb6, #48f585);
        background-size: 300% 300%; animation: skillPulse 6s ease infinite;
        color: white; padding: 0.6rem 1.2rem; border-radius: 25px; margin: 0.3rem;
        display: inline-block; font-weight: 500;
        box-shadow: 0 4px 15px rgba(17,153,142,0.4); transition: all 0.3s ease;
    }
    .skill-optimizable {
        background: linear-gradient(135deg, #4facfe, #00f2fe, #667eea, #764ba2);
        background-size: 300% 300%; animation: skillPulse 6s ease infinite;
        color: white; padding: 0.6rem 1.2rem; border-radius: 25px; margin: 0.3rem;
        display: inline-block; font-weight: 500;
        box-shadow: 0 4px 15px rgba(79,172,254,0.4); transition: all 0.3s ease;
    }
    .skill-missing {
        background: linear-gradient(135deg, #f857a6, #ff5858, #ff6a88, #ff9966);
        background-size: 300% 300%; animation: missingPulse 6s ease infinite;
        color: white; padding: 0.6rem 1.2rem; border-radius: 25px; margin: 0.3rem;
        display: inline-block; font-weight: 500;
        box-shadow: 0 4px 15px rgba(248,87,166,0.4); transition: all 0.3s ease;
    }
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,380..560&family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

  :root{
    --navy-0:#0B0D14; --navy-1:#12151F; --navy-2:#1A1F2E; --navy-3:#242B3F; --navy-4:#323B54;
    --paper:#F1EBDC; --paper-ink:#201D16; --paper-line:rgba(32,29,22,.14);
    --cream:#ECEAE2; --mist:#8A93AA; --mist-dim:#5C647A;
    --amber:#F0A93B; --amber-deep:#C67E1E; --amber-glow:rgba(240,169,59,.35);
    --teal:#3FC79A; --teal-deep:#1F9A73; --teal-glow:rgba(63,199,154,.28);
    --coral:#FF6E5C; --coral-deep:#D6503F; --coral-glow:rgba(255,110,92,.28);
    --indigo:#8A8BF0; --indigo-deep:#5F60C9; --indigo-glow:rgba(138,139,240,.3);
    --f-display:'Fraunces',Georgia,serif;
    --f-sans:'Space Grotesk','Segoe UI',Helvetica,Arial,sans-serif;
    --f-mono:'JetBrains Mono','SFMono-Regular',Consolas,monospace;
    --ease:cubic-bezier(.22,.9,.25,1);
    --ease-spring:cubic-bezier(.34,1.56,.64,1);
  }

  /* Override Streamlit root to make background transparent and apply font */
  .stApp, .stAppHeader { 
      background: transparent !important; 
      font-family: var(--f-sans) !important; 
      color: var(--cream) !important;
  }
  
  /* Make the body itself carry the base color just in case */
  body { background: var(--navy-0); }
  
  /* Hide standard streamlit elements */
  #MainMenu, header[data-testid="stHeader"] { visibility: hidden; }
  
  ::selection{background:var(--amber);color:#20150a;}

  /* ================= AMBIENT 3D BACKDROP ================= */
  .bg-fx{position:fixed;inset:0;z-index:-1;pointer-events:none;overflow:hidden;}
  .glow{position:absolute;border-radius:50%;filter:blur(70px);opacity:.55;}
  .glow.g1{width:520px;height:520px;background:var(--amber-glow);top:-180px;left:-120px;}
  .glow.g2{width:460px;height:460px;background:var(--indigo-glow);top:280px;right:-160px;}
  .glow.g3{width:420px;height:420px;background:var(--teal-glow);bottom:-200px;left:30%;}
  .floor-grid{
    position:absolute;left:0;right:0;bottom:-40%;height:80%;
    background-image:
      linear-gradient(var(--navy-3) 1px, transparent 1px),
      linear-gradient(90deg, var(--navy-3) 1px, transparent 1px);
    background-size:52px 52px;
    transform:perspective(600px) rotateX(62deg);
    opacity:.22; mask-image:linear-gradient(to top, black, transparent 75%);
    transition:transform .1s linear;
  }

  /* floating 3D orbit shapes */
  .orbit{position:absolute;opacity:.5;will-change:transform;}
  .orbit .spin{width:100%;height:100%;transform-style:preserve-3d;}
  .orbit svg{width:100%;height:100%;filter:drop-shadow(0 20px 30px rgba(0,0,0,.35));}
  .orbit.o1{width:150px;height:150px;top:12%;right:8%;perspective:900px;}
  .orbit.o1 .spin{animation:spinA 22s linear infinite;}
  .orbit.o2{width:110px;height:110px;top:58%;left:4%;perspective:800px;}
  .orbit.o2 .spin{animation:spinB 26s linear infinite;}
  .orbit.o3{width:90px;height:90px;top:34%;left:46%;perspective:700px;}
  .orbit.o3 .spin{animation:spinC 19s linear infinite;}
  @keyframes spinA{0%{transform:rotateX(15deg) rotateY(0deg);}100%{transform:rotateX(15deg) rotateY(360deg);}}
  @keyframes spinB{0%{transform:rotateX(0deg) rotateY(0deg) rotateZ(8deg);}100%{transform:rotateX(360deg) rotateY(0deg) rotateZ(8deg);}}
  @keyframes spinC{0%{transform:rotateX(-10deg) rotateY(0deg);}100%{transform:rotateX(-10deg) rotateY(-360deg);}}

  /* Typography Overrides */
  .main-header {
    font-family:var(--f-display);font-optical-sizing:auto;font-weight:480;
    font-size:clamp(32px,3.6vw,42px);letter-spacing:-0.01em;margin:0 0 10px;
    color: var(--cream);
  }
  .sub-header {
    color:var(--mist);font-size:16px;margin:0 0 30px; font-family: var(--f-sans);
  }
  h1, h2, h3, h4, h5, h6 { font-family: var(--f-display) !important; color: var(--cream) !important; }
  p, div, span, label { font-family: var(--f-sans); color: var(--cream); }
  label p { font-size: 14px !important; color: var(--mist) !important; }

  /* Map Streamlit containers to Parity .panel style */
  div[data-testid="stFileUploader"] {
    background:linear-gradient(165deg, var(--navy-2), var(--navy-1));
    border:1px solid var(--navy-4);border-radius:14px;padding:20px;
    box-shadow:0 30px 60px -30px rgba(0,0,0,.6), inset 0 1px 0 rgba(255,255,255,.03);
  }
  div[data-testid="stFileUploader"] section { background: var(--navy-0) !important; border:1.5px dashed var(--navy-4) !important; border-radius:10px !important; }
  div[data-testid="stFileUploader"] section:hover { border-color: var(--amber-deep) !important; }

  div[data-testid="stTextArea"] {
    background:linear-gradient(165deg, var(--navy-2), var(--navy-1));
    border:1px solid var(--navy-4);border-radius:14px;padding:20px;
    box-shadow:0 30px 60px -30px rgba(0,0,0,.6), inset 0 1px 0 rgba(255,255,255,.03);
  }
  div[data-testid="stTextArea"] textarea {
    background:var(--navy-0); border:1px solid var(--navy-4); border-radius:10px; padding:14px;
    font-family:var(--f-mono); font-size:12px; color:var(--mist);
  }
  div[data-testid="stTextArea"] textarea:focus { border-color: var(--amber) !important; box-shadow: none !important; }

  /* Fix Multiselect Dropdown Text Color Visibility */
  div[data-baseweb="select"] ul, div[role="listbox"] {
      background-color: var(--navy-1) !important;
  }
  div[data-baseweb="select"] li, div[role="option"] {
      color: var(--cream) !important;
  }
  span[data-baseweb="tag"] {
      background-color: var(--navy-3) !important;
      color: var(--cream) !important;
  }

  /* Parity Buttons */
  div[data-testid="stButton"] button {
    font-family:var(--f-sans) !important;font-weight:700 !important;font-size:15px !important;color:#241602 !important;
    background:linear-gradient(180deg,#FFC15C,var(--amber)) !important;border:none !important;border-radius:10px !important;
    padding:10px 26px !important;cursor:pointer !important;
    box-shadow:0 1px 0 rgba(255,255,255,.4) inset, 0 14px 28px -10px var(--amber-glow) !important;
    transition:transform .18s var(--ease) !important;
  }
  div[data-testid="stButton"] button:hover { transform:translateY(-2px) translateZ(4px) !important; }

  div[data-testid="stDownloadButton"] button {
    background:var(--navy-2) !important;border:1px solid var(--navy-4) !important;
    color:var(--cream) !important;
    border-radius:11px !important;padding:14px 20px !important; font-size:14px !important;font-weight:600 !important;
    transition:transform .18s var(--ease), background .18s var(--ease), box-shadow .18s var(--ease) !important;
  }
  div[data-testid="stDownloadButton"] button:hover { background:var(--navy-3) !important;box-shadow:0 16px 30px -14px rgba(0,0,0,.6) !important; transform:translateY(-3px) !important; }

  /* Map Streamlit metrics to Parity .stat-card style */
  div[data-testid="stMetric"] {
    background:linear-gradient(165deg, var(--navy-2), var(--navy-1));
    border:1px solid var(--navy-4);
    box-shadow:0 24px 46px -22px rgba(0,0,0,.6), inset 0 1px 0 rgba(255,255,255,.03);
    border-radius:14px; padding:20px 18px;
    transition:box-shadow .3s var(--ease);
  }
  div[data-testid="stMetric"]:hover { box-shadow:0 30px 60px -20px rgba(0,0,0,.7); }
  div[data-testid="stMetricLabel"] { font-size:11.5px !important;color:var(--mist) !important;font-family:var(--f-mono) !important; text-transform: uppercase; margin-bottom:12px; }
  div[data-testid="stMetricValue"] { font-family:var(--f-mono) !important;font-weight:700 !important;font-size:28px !important;color:var(--cream) !important; }
  
  /* Skills Badges (Chips) */
  .skill-listed {
    background:linear-gradient(165deg, rgba(63,199,154,.22), rgba(63,199,154,.08));
    color:var(--teal);border:1px solid rgba(63,199,154,.4);box-shadow:0 6px 14px -6px var(--teal-glow);
    font-size:12.5px;font-weight:500;padding:7px 13px;border-radius:20px;display:inline-block; margin: 0.2rem;
  }
  .skill-optimizable {
    background:linear-gradient(165deg, rgba(138,139,240,.22), rgba(138,139,240,.08));
    color:var(--indigo);border:1px solid rgba(138,139,240,.4);box-shadow:0 6px 14px -6px var(--indigo-glow);
    font-size:12.5px;font-weight:500;padding:7px 13px;border-radius:20px;display:inline-block; margin: 0.2rem;
  }
  .skill-missing {
    background:transparent;color:var(--coral);border:1.3px dashed rgba(255,110,92,.55);
    font-size:12.5px;font-weight:500;padding:7px 13px;border-radius:20px;display:inline-block; margin: 0.2rem;
  }
  
  hr { border-color: var(--navy-4) !important; margin: 2rem 0; }

  /* Info / Warning Banners */
  div[data-testid="stAlert"] { background: var(--navy-2) !important; border: 1px solid var(--navy-4) !important; color: var(--mist) !important; border-radius: 12px; }
  div[data-baseweb="toast"] { background: var(--navy-2) !important; border: 1px solid var(--teal) !important; }

</style>

<!-- INJECT BACKGROUND DOM INTO STREAMLIT -->
<div class="bg-fx">
  <div class="glow g1"></div>
  <div class="glow g2"></div>
  <div class="glow g3"></div>
  <div class="floor-grid" id="floorGrid"></div>

  <div class="orbit o1" id="orbit1"><div class="spin">
    <svg viewBox="0 0 100 100" fill="none"><rect x="12" y="12" width="76" height="76" rx="10" stroke="#F0A93B" stroke-width="2" stroke-opacity=".5"/><rect x="28" y="28" width="44" height="44" rx="6" stroke="#F0A93B" stroke-width="1.4" stroke-opacity=".3"/></svg>
  </div></div>
  <div class="orbit o2" id="orbit2"><div class="spin">
    <svg viewBox="0 0 100 100" fill="none"><circle cx="50" cy="50" r="38" stroke="#8A8BF0" stroke-width="2" stroke-opacity=".45"/><circle cx="50" cy="50" r="20" stroke="#8A8BF0" stroke-width="1.4" stroke-opacity=".3"/></svg>
  </div></div>
  <div class="orbit o3" id="orbit3"><div class="spin">
    <svg viewBox="0 0 100 100" fill="none"><path d="M50 6l44 25v38L50 94 6 69V31z" stroke="#3FC79A" stroke-width="2" stroke-opacity=".4"/></svg>
  </div></div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# SEO / verification meta tags
# ---------------------------------------------------------------------------
st.markdown("""
<meta name="google-site-verification" content="7jwm2GgyD0Poye-jsetxuXy24KI9oolYu3tIQZ-wbpY" />
<meta name="description" content="Free AI Resume Optimizer — get your ATS score, identify missing skills, and download a skills-optimised resume. No API key required.">
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Imports (deferred — keeps startup fast)
# ---------------------------------------------------------------------------
from core.parser import parse_resume, parse_job_description, classify_skills
from core.role_detector import detect_role, extract_top_skills
from utils.ai_skill_matcher import ai_matcher, _load_keyword_processor
from utils.document_generator import create_cover_letter_docx, create_ats_report_docx
from utils.inplace_editor import edit_docx_skills, edit_pdf_skills
from utils.dynamic_skills import extract_skills_with_llm, update_local_db, generate_improvement_tips
import json, os

# Load static data once
@st.cache_resource
def _load_archetypes():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "data", "role_archetypes.json"), "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_resource
def _load_synonym_map_cached():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "data", "synonym_map.json"), "r", encoding="utf-8") as f:
        return json.load(f)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown('<div class="main-header">AI Resume Optimizer</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Upload your resume and the job post.<br>Our engine scores the match instantly — nothing leaves your session until you choose to download.</div>', unsafe_allow_html=True)



# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False

# ---------------------------------------------------------------------------
# Input section
# ---------------------------------------------------------------------------
col1, col2 = st.columns([1, 1])

with col1:
    st.markdown("#### 📤 Upload Resume")
    uploaded_file = st.file_uploader(
        "Choose file", type=["pdf", "docx"], label_visibility="collapsed"
    )

with col2:
    st.markdown("#### 📋 Paste Job Description")
    job_description = st.text_area(
        "Job Description",
        height=200,
        placeholder="Paste the full job description here…",
        label_visibility="collapsed",
    )

# ---------------------------------------------------------------------------
# Analyze button
# ---------------------------------------------------------------------------
if st.button("🚀 Analyze", type="primary"):
    if not uploaded_file:
        st.error("⬆️ Please upload a resume first.")
    elif not job_description or len(job_description.strip()) < 20:
        st.error("📋 Please paste a job description (at least 20 characters).")
    else:
        with st.status("Analyzing your resume...", expanded=True) as status:
            import time
            start_time = time.time()
            budget = 30.0

            st.write("Building skill index and extracting text...")
            kp = _load_keyword_processor()
            archetypes = _load_archetypes()
            synonym_map = _load_synonym_map_cached()

            resume_bytes = uploaded_file.read()
            resume_filename = uploaded_file.name
            resume_out = parse_resume(resume_bytes, resume_filename, keyword_processor=kp)

            if not resume_out.get("text", "").strip():
                status.update(label="Extraction failed", state="error")
                st.error("❌ Could not extract any text from your resume. Please check the file format.")
                st.stop()

            st.write("Parsing job description...")
            job_keywords = parse_job_description(job_description, keyword_processor=kp)

            st.write("Running local ATS scoring...")
            role_result = detect_role(job_description, archetypes=archetypes, synonym_map=synonym_map)
            archetype_data = role_result["archetype_data"]

            score_data = ai_matcher.calculate_enhanced_ats_score(
                resume_skills=resume_out.get("skills_full", resume_out.get("skills", [])),
                job_keywords=job_keywords,
                archetype_data=archetype_data,
                resume_text=resume_out.get("text", ""),
                jd_text=job_description,
            )

            # Three-bucket classification
            all_jd_skills = list(dict.fromkeys(
                (job_keywords.get("must_have") or []) +
                (job_keywords.get("nice_to_have") or [])
            ))
            skill_buckets = classify_skills(
                jd_skills=all_jd_skills,
                skills_full=resume_out.get("skills_full", resume_out.get("skills", [])),
                skills_in_skills_section=resume_out.get("skills_in_skills_section", []),
                synonym_map=synonym_map,
            )

            llm_skills = None
            tips = ""

            # Use local model at first. Only use LLM extraction if local model missed skills (found < 5)
            if len(job_keywords.get("must_have", [])) < 5 and (time.time() - start_time < (budget - 8.0)):
                st.write("Fetching AI-powered skills...")
                llm_skills = extract_skills_with_llm(job_description, start_time, budget)
                if llm_skills is not None:
                    # LLM succeeded. Override the locally extracted skills
                    job_keywords["must_have"] = llm_skills
                    job_keywords["nice_to_have"] = []
                    job_keywords["raw_skills"] = llm_skills
                    # Still learn new skills not in local DB!
                    update_local_db(llm_skills)
                    
                    # Re-run scoring with new LLM skills
                    score_data = ai_matcher.calculate_enhanced_ats_score(
                        resume_skills=resume_out.get("skills_full", resume_out.get("skills", [])),
                        job_keywords=job_keywords,
                        archetype_data=archetype_data,
                        resume_text=resume_out.get("text", ""),
                        jd_text=job_description,
                    )
                    all_jd_skills = list(dict.fromkeys(
                        (job_keywords.get("must_have") or []) +
                        (job_keywords.get("nice_to_have") or [])
                    ))
                    skill_buckets = classify_skills(
                        jd_skills=all_jd_skills,
                        skills_full=resume_out.get("skills_full", resume_out.get("skills", [])),
                        skills_in_skills_section=resume_out.get("skills_in_skills_section", []),
                        synonym_map=synonym_map,
                    )

            if time.time() - start_time < (budget - 8.0):
                st.write("Fetching AI-powered tips...")
                genuinely_missing = skill_buckets.get("genuinely_missing", [])
                if genuinely_missing:
                    tips = generate_improvement_tips(genuinely_missing, job_keywords.get("job_title", "Technical Role"), are_missing=True, start_time=start_time, time_budget=budget)
                else:
                    top_skills = job_keywords.get("must_have", [])[:5]
                    if top_skills:
                        tips = generate_improvement_tips(top_skills, job_keywords.get("job_title", "Technical Role"), are_missing=False, start_time=start_time, time_budget=budget)

            if llm_skills is None or not tips:
                status.update(label="Analysis complete! (AI tips unavailable — showing local analysis)", state="complete")
            else:
                status.update(label="Analysis complete!", state="complete")

        # Surface extraction quality warning
        quality = resume_out.get("quality", {})
        if not quality.get("ok", True):
            st.warning(quality.get("warning", "⚠️ Resume extraction quality warning."))

        if not job_keywords.get("must_have") and not job_keywords.get("raw_skills"):
            st.warning("⚠️ No specific skills detected in the job description. Results may be limited.")

        # Store in session state
        st.session_state.resume_text        = resume_out["text"]
        st.session_state.resume_sections    = resume_out.get("sections", {})
        st.session_state.resume_skills_full = resume_out.get("skills_full", resume_out.get("skills", []))
        st.session_state.resume_skills_listed = resume_out.get("skills_in_skills_section", [])
        st.session_state.job_keywords       = job_keywords
        st.session_state.score_data         = score_data
        st.session_state.role_result        = role_result
        st.session_state.archetype_data     = archetype_data
        st.session_state.skill_buckets      = skill_buckets
        st.session_state.improvement_tips   = tips
        st.session_state.resume_bytes       = resume_bytes   # original bytes for in-place edit
        st.session_state.resume_filename    = resume_filename
        st.session_state.skills_section_warning = resume_out.get("skills_section_warning", "")
        st.session_state.skills_heading_label   = resume_out.get("skills_heading_label", "")
        st.session_state.analysis_done      = True

        st.rerun()

# ---------------------------------------------------------------------------
# Results section
# ---------------------------------------------------------------------------
if st.session_state.analysis_done:
    score_data      = st.session_state.score_data
    resume_text     = st.session_state.resume_text
    resume_sections = st.session_state.get("resume_sections", {})
    job_keywords    = st.session_state.job_keywords
    role_result     = st.session_state.role_result
    archetype_data  = st.session_state.archetype_data
    skill_buckets   = st.session_state.get("skill_buckets", {})
    resume_bytes    = st.session_state.get("resume_bytes", b"")
    resume_filename = st.session_state.get("resume_filename", "resume.pdf")
    skills_section_warning = st.session_state.get("skills_section_warning", "")
    skills_heading_label   = st.session_state.get("skills_heading_label", "")

    st.markdown("---")

    # === Metric cards row ===
    cols = st.columns(5)
    with cols[0]:
        st.metric("ATS SCORE", f"{score_data['ats_score']}%")
    with cols[1]:
        st.metric("MATCHED", f"{score_data['matched_count']}/{score_data['total_keywords']}")
    with cols[2]:
        st.metric("MISSING", score_data["missing_count"])
    with cols[3]:
        st.metric("VS AVG APPLICANT", f"{score_data['ats_score'] - 67:+}%")
    with cols[4]:
        display_name = archetype_data.get("display_name", "General")
        st.metric("ROLE DETECTED", display_name)

    st.markdown("---")

    # === Score breakdown ===
    with st.expander("📊 Score Breakdown"):
        b1, b2 = st.columns(2)
        with b1:
            st.metric("Skill Match (60%)", f"{score_data['weighted_skill_score']}%")
        with b2:
            st.metric("TF-IDF (40%)", f"{score_data['tfidf_score']}%")

    tips = st.session_state.get("improvement_tips", "")
    if tips:
        st.info(f"💡 **How to improve your TF-IDF & Overall Score:**\n\n{tips}")

    st.markdown("---")

    # === Three-bucket skill display ===
    already   = skill_buckets.get("already_listed", [])
    optimizable = skill_buckets.get("optimizable", [])
    genuinely_missing = skill_buckets.get("genuinely_missing", [])

    # Surface skills-section detection status
    if skills_section_warning:
        st.warning(skills_section_warning)
    elif skills_heading_label:
        st.info(f"🔍 Skills section detected under heading: **\"{skills_heading_label}\"**")

    col_a, col_b = st.columns(2)

    with col_a:
        st.write("**✅ Skills in Resume**")
        combined_resume_skills = already + optimizable
        if combined_resume_skills:
            for skill in combined_resume_skills:
                st.write(f'<span class="skill-listed">{skill}</span>', unsafe_allow_html=True)
        else:
            st.write("None detected")

    with col_b:
        st.write("**⚠️ Missing Keywords or Skills to Add**")
        st.caption("These appear in the JD but were NOT found anywhere in your resume.")
        if genuinely_missing:
            for skill in genuinely_missing:
                st.write(f'<span class="skill-missing">{skill}</span>', unsafe_allow_html=True)
        else:
            st.write("None — full coverage! 🎉")

    st.markdown("---")

    # === Downloads ===
    tab1, tab2, tab3 = st.tabs(["📥 Download", "ℹ️ Job Info", "❓ Help"])

    with tab1:
        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("**📄 Optimised Resume**")
            st.caption(
                "Only the Technical Skills section is changed — everything else is byte-identical to your upload."
            )

            all_injectable = optimizable + genuinely_missing
            if not all_injectable:
                st.info("✅ Your resume already lists all skills — the original file is downloaded unchanged.")
                skills_to_add = []
            else:
                st.markdown("### 🛠️ Select Skills to Add")
                st.markdown("Select any missing skills you want to inject into your Skills section:")
                
                # Default to picking the first 2 skills as requested
                default_skills = all_injectable[:2] if len(all_injectable) >= 2 else all_injectable
                
                skills_to_add = st.multiselect(
                    "Skills to inject:",
                    options=all_injectable,
                    default=default_skills,
                    label_visibility="collapsed"
                )

            # Build the in-place edited file
            with st.spinner("Applying skill optimizations…"):
                try:
                    is_pdf = resume_filename.lower().endswith(".pdf")
                    is_docx = resume_filename.lower().endswith(".docx")

                    if is_docx:
                        out_bytes, was_changed, before, after = edit_docx_skills(
                            resume_bytes, skills_to_add
                        )
                        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        ext = ".docx"
                    elif is_pdf:
                        out_bytes, was_changed, before, after = edit_pdf_skills(
                            resume_bytes, skills_to_add
                        )
                        mime = "application/pdf"
                        ext = ".pdf"
                    else:
                        out_bytes, was_changed, before, after = resume_bytes, False, "", ""
                        mime = "application/octet-stream"
                        ext = ""

                    out_name = resume_filename.rsplit(".", 1)[0] + f"_optimized{ext}"

                    if was_changed and before and after:
                        with st.expander("🔍 Skills Section Change Preview"):
                            st.markdown("**Before:**")
                            st.code(before, language=None)
                            st.markdown("**After:**")
                            st.code(after, language=None)

                    st.download_button(
                        label="📄 Download Optimised Resume",
                        data=out_bytes,
                        file_name=out_name,
                        mime=mime,
                    )

                except Exception as e:
                    st.error(f"Error applying optimizations: {e}")
                    # Fallback: offer original unchanged
                    if resume_bytes:
                        st.download_button(
                            label="📄 Download Original Resume",
                            data=resume_bytes,
                            file_name=resume_filename,
                            mime="application/octet-stream",
                        )

        with c2:
            letter_docx = create_cover_letter_docx(
                resume_text, job_keywords, score_data, archetype_data=archetype_data
            )
            st.download_button(
                "📝 Cover Letter",
                data=letter_docx,
                file_name="CoverLetter.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        with c3:
            report_docx = create_ats_report_docx(
                score_data,
                job_keywords,
                archetype_data=archetype_data,
                skill_buckets=skill_buckets,
            )
            st.download_button(
                "📊 ATS Report",
                data=report_docx,
                file_name="ATS_Report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

    with tab2:
        st.write(f"**Job:** {job_keywords.get('job_title', 'N/A')}")
        st.write(f"**Company:** {job_keywords.get('company', 'N/A')}")
        st.write(f"**Level:** {job_keywords.get('experience', 'N/A')}")
        st.write(f"**Must-Have Skills:** {len(job_keywords.get('must_have', []))}")
        st.write(f"**Detected Archetype:** {archetype_data.get('display_name', 'N/A')} (confidence: {role_result.get('confidence', 0)} keyword hits)")

    with tab3:
        st.write("1. Upload resume (PDF or DOCX)")
        st.write("2. Paste the full job description")
        st.write("3. Click **Analyze**")
        st.write("4. Review your ATS score and three-bucket skill breakdown")
        st.write("5. Download your optimised resume — only the Skills section is changed")
        st.write("---")
        st.write("**💡 How skills are classified:**")
        st.write("- ✅ **Already Listed** — skill is already in your Technical Skills section")
        st.write("- 🔄 **Will Be Added** — skill is evidenced in your Experience/Projects, added to Skills section")
        st.write("- ⚠️ **Advisory Only** — skill is in the JD but nowhere in your resume; NOT added to the file")
        st.write("---")
        st.write("**💡 For best results:** Use a single-column, text-selectable PDF resume (no tables or images).")

# ---------------------------------------------------------------------------
# Adsterra Banner Ad (bottom)
# ---------------------------------------------------------------------------
components.html("""
<div style="text-align: center; margin: 30px 0;">
<script type="text/javascript">
atOptions = {
  'key' : '0fffadfc8b3463520518a4244ad1f554',
  'format' : 'iframe',
  'height' : 90,
  'width' : 728,
  'params' : {}
};
</script>
<script type="text/javascript" src="//www.highperformanceformat.com/0fffadfc8b3463520518a4244ad1f554/invoke.js"></script>
</div>
""", height=120)
