"""
utils/inplace_editor.py
=======================
In-place resume skill editor.

Only ever modifies the Technical Skills section of the ORIGINAL uploaded
file.  Every other byte of the document is left untouched.

Public API
----------
edit_docx_skills(file_bytes, optimizable_skills)
    -> (out_bytes, was_changed, skills_text_before, skills_text_after)

edit_pdf_skills(file_bytes, optimizable_skills)
    -> (out_bytes, was_changed, skills_text_before, skills_text_after)

Rules
-----
- OPTIMIZABLE skills (evidenced elsewhere in the resume but not in the
  Skills section) are appended to the existing skill list, comma-separated,
  matching the existing formatting style.
- If optimizable_skills is empty, the original bytes are returned unchanged
  and was_changed=False.
- No other paragraph, heading, or section is ever touched.
- Output format always matches input format — no docx↔pdf conversion.
"""

import io
import re


# ---------------------------------------------------------------------------
# Heading patterns to identify the Technical Skills section
# ---------------------------------------------------------------------------

_SKILLS_HEADING_PATTERN = re.compile(
    r"^(technical\s+skills?|skills?|core\s+competencies|competencies|"
    r"technologies|expertise|key\s+skills?|relevant\s+skills?|"
    r"technical\s+proficiencies|areas\s+of\s+expertise|"
    r"professional\s+skills?|hard\s+skills?|software\s+skills?|"
    r"programming\s+skills?)\s*:?\s*$",
    re.IGNORECASE,
)

_SKILLS_HEADING_INLINE_PATTERN = re.compile(
    r"^(technical\s+skills?|skills?|core\s+competencies|competencies|"
    r"technologies|expertise|key\s+skills?|relevant\s+skills?|"
    r"technical\s+proficiencies|areas\s+of\s+expertise|"
    r"professional\s+skills?|hard\s+skills?|software\s+skills?|"
    r"programming\s+skills?)\s*[:\-\u2013]\s*",
    re.IGNORECASE,
)


def _canonicalize(skill: str) -> str:
    """Lowercase + strip for dedup comparison."""
    return skill.lower().strip()


# ---------------------------------------------------------------------------
# DOCX in-place editor
# ---------------------------------------------------------------------------

def edit_docx_skills(
    file_bytes: bytes,
    optimizable_skills: list,
) -> tuple:
    """
    Append optimizable_skills to the Technical Skills paragraph(s) of a DOCX.

    Returns
    -------
    (out_bytes: bytes, was_changed: bool,
     skills_text_before: str, skills_text_after: str)
    """
    if not optimizable_skills:
        return file_bytes, False, "", ""

    import docx
    from docx.oxml.ns import qn

    doc = docx.Document(io.BytesIO(file_bytes))
    paragraphs = doc.paragraphs

    # ── Locate the skills heading and the paragraph(s) that follow it ──────
    # Strategy:
    #   Pass 1: find a standalone heading paragraph that matches the skills
    #           heading pattern (e.g. "Technical Skills" on its own line).
    #   Pass 2: find an inline "Technical Skills: ..." paragraph where the
    #           skills are listed on the same line as the heading.

    skills_para_indices = []   # indices of content paragraphs to extend
    inline_heading_idx = None  # index of inline heading paragraph (pass 2)
    heading_idx = None

    for i, para in enumerate(paragraphs):
        stripped = para.text.strip()
        if _SKILLS_HEADING_PATTERN.match(stripped):
            heading_idx = i
            break
        if _SKILLS_HEADING_INLINE_PATTERN.match(stripped):
            inline_heading_idx = i
            break

    if heading_idx is not None:
        # Collect content paragraphs immediately following the heading,
        # stopping at the next heading or blank line after content.
        j = heading_idx + 1
        while j < len(paragraphs):
            text = paragraphs[j].text.strip()
            # Stop at next section heading
            if _is_section_heading(paragraphs[j]):
                break
            if text:
                skills_para_indices.append(j)
            j += 1

    elif inline_heading_idx is not None:
        skills_para_indices = [inline_heading_idx]
    else:
        # No skills section found — return original unchanged
        return file_bytes, False, "", ""

    if not skills_para_indices:
        return file_bytes, False, "", ""

    # Use the last non-empty skills paragraph as the append target
    target_idx = skills_para_indices[-1]
    target_para = paragraphs[target_idx]
    original_text = target_para.text

    # ── Build the dedup set from existing skills text ─────────────────────
    # Extract all comma/semicolon/pipe/colon separated tokens as "already listed"
    existing_tokens = {
        _canonicalize(t)
        for t in re.split(r"[,;|•\n:/]+", original_text)
        if t.strip()
    }

    # Filter out skills already present and title case them for consistency
    new_skills = []
    for s in optimizable_skills:
        if _canonicalize(s) not in existing_tokens:
            new_skills.append(s.title())
            existing_tokens.add(_canonicalize(s))

    if not new_skills:
        return file_bytes, False, original_text, original_text

    # ── Detect separator style from existing text ─────────────────────────
    separator = ", "
    if ";" in original_text:
        separator = "; "
    elif " | " in original_text:
        separator = " | "

    # ── Append to the last run of the target paragraph ────────────────────
    skills_text_before = original_text.strip()
    addition = separator + separator.join(new_skills)

    # Try to append to the last run to preserve formatting
    if target_para.runs:
        target_para.runs[-1].text += addition
    else:
        target_para.add_run(addition)

    skills_text_after = target_para.text.strip()

    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    return out.read(), True, skills_text_before, skills_text_after


def _is_section_heading(para) -> bool:
    """Heuristic: bold short line or a known heading style."""
    style_name = (para.style.name or "").lower() if para.style else ""
    if "heading" in style_name:
        return True
    text = para.text.strip()
    if not text or len(text) > 80:
        return False
    # All runs bold and short → treat as heading
    runs = [r for r in para.runs if r.text.strip()]
    if runs and all(r.bold for r in runs) and len(text) < 50:
        return True
    # Known section words appearing on their own line
    return bool(re.match(
        r"^(experience|education|projects|certifications|summary|"
        r"objective|profile|achievements|awards|publications|"
        r"professional experience|work experience)\s*:?\s*$",
        text,
        re.IGNORECASE,
    ))


# ---------------------------------------------------------------------------
# PDF in-place editor (PyMuPDF / fitz)
# ---------------------------------------------------------------------------

def edit_pdf_skills(
    file_bytes: bytes,
    optimizable_skills: list,
) -> tuple:
    """
    Append optimizable_skills to the Technical Skills text block in a PDF.

    Uses a redact-and-redraw strategy:
      1. Locate the skills heading using page.search_for()
      2. Find the text block immediately below it (the skills list)
      3. Redact (white-box) that block
      4. Re-draw the full updated skills line in the same position / font

    Returns
    -------
    (out_bytes: bytes, was_changed: bool,
     skills_text_before: str, skills_text_after: str)
    """
    if not optimizable_skills:
        return file_bytes, False, "", ""

    try:
        import fitz  # PyMuPDF
    except ImportError:
        # PyMuPDF not installed — return original unchanged
        return file_bytes, False, "", ""

    doc = fitz.open(stream=file_bytes, filetype="pdf")

    # Heading keywords to search for (try most specific first, then generic)
    heading_candidates = [
        "Technical Skills",
        "TECHNICAL SKILLS",
        "Relevant Skills",
        "RELEVANT SKILLS",
        "Core Competencies",
        "CORE COMPETENCIES",
        "Key Skills",
        "KEY SKILLS",
        "Technical Proficiencies",
        "TECHNICAL PROFICIENCIES",
        "Areas of Expertise",
        "AREAS OF EXPERTISE",
        "Professional Skills",
        "PROFESSIONAL SKILLS",
        "Skills",
        "SKILLS",
    ]

    was_changed = False
    skills_text_before = ""
    skills_text_after = ""

    for page in doc:
        heading_rect = None
        heading_text_found = None

        for heading_label in heading_candidates:
            hits = page.search_for(heading_label)
            if hits:
                heading_rect = hits[0]  # first occurrence
                heading_text_found = heading_label
                break

        if heading_rect is None:
            continue  # try next page

        # ── Find the text block immediately below the heading ─────────────
        # Get all text blocks on this page sorted top-to-bottom
        blocks = page.get_text("blocks", sort=True)
        # blocks: list of (x0, y0, x1, y1, text, block_no, block_type)
        skills_block = None
        heading_bottom = heading_rect.y1

        for block in blocks:
            bx0, by0, bx1, by1, btext, *_ = block
            btext = btext.strip()
            if not btext:
                continue
            # Skip blocks that end above the heading (e.g. previous sections in a column)
            if by1 <= heading_rect.y0:
                continue
            # Skip the heading block itself
            if _SKILLS_HEADING_PATTERN.match(btext) or _SKILLS_HEADING_INLINE_PATTERN.match(btext):
                continue
            if heading_text_found in btext and len(btext) < len(heading_text_found) + 10:
                continue
            # Skip very short blocks that are likely just decorative lines
            if len(btext) < 3:
                continue
            skills_block = block
            break

        if skills_block is None:
            continue

        bx0, by0, bx1, by1, btext, *_ = skills_block
        original_skills_text = btext.strip()
        skills_text_before = original_skills_text

        # ── Dedup ──────────────────────────────────────────────────────────
        existing_tokens = {
            _canonicalize(t)
            for t in re.split(r"[,;|•\n:/]+", original_skills_text)
            if t.strip()
        }
        new_skills = []
        for s in optimizable_skills:
            if _canonicalize(s) not in existing_tokens:
                new_skills.append(s.title())
                existing_tokens.add(_canonicalize(s))

        if not new_skills:
            skills_text_after = original_skills_text
            break

        # ── Detect separator ───────────────────────────────────────────────
        separator = ", "
        if ";" in original_skills_text:
            separator = "; "
        elif " | " in original_skills_text:
            separator = " | "

        updated_text = original_skills_text.rstrip() + separator + separator.join(new_skills)
        skills_text_after = updated_text

        # ── Detect font properties of the skills block ─────────────────────
        font_size = 10.0
        font_name = "helv"
        text_color = (0, 0, 0)  # default black

        try:
            detail = page.get_text("dict", clip=fitz.Rect(bx0, by0, bx1, by1))
            for blk in detail.get("blocks", []):
                for line in blk.get("lines", []):
                    for span in line.get("spans", []):
                        if span.get("size"):
                            font_size = span["size"]
                        if span.get("font"):
                            fn = span["font"].lower()
                            # Map to a fitz-safe base font name
                            if "bold" in fn and "italic" in fn:
                                font_name = "tibo"
                            elif "bold" in fn:
                                font_name = "helv"  # helvetica (close enough)
                            elif "italic" in fn:
                                font_name = "tiit"
                            else:
                                font_name = "helv"
                        c = span.get("color", 0)
                        if isinstance(c, int):
                            r = (c >> 16) & 0xFF
                            g = (c >> 8) & 0xFF
                            b = c & 0xFF
                            text_color = (r / 255, g / 255, b / 255)
                        break
                    break
                break
        except Exception:
            pass

        # ── Redact (white-box) the existing skills block ───────────────────
        redact_rect = fitz.Rect(bx0, by0, bx1, by1)
        page.add_redact_annot(redact_rect, fill=(1, 1, 1))
        page.apply_redactions()

        # ── Re-draw the updated skills text ───────────────────────────────
        # Use insert_textbox to automatically word-wrap the text.
        # We give it a small height allowance (+5) to prevent overlapping with next sections.
        right_margin = page.rect.width - bx0
        # If the original block had a wider bounding box, use that instead
        right_boundary = max(right_margin, bx1) if bx1 > bx0 else right_margin
        
        textbox_rect = fitz.Rect(bx0, by0, right_boundary, by1 + 5)
        
        # Remove existing newlines since insert_textbox will handle wrapping
        # but keep paragraph breaks if there were double newlines (rare for skills).
        # We'll just replace single newlines with spaces to let it wrap naturally.
        wrapped_text = updated_text.replace('\n', ' ')
        
        page.insert_textbox(
            textbox_rect,
            wrapped_text,
            fontname=font_name,
            fontsize=max(font_size - 0.5, 8.0),
            color=text_color,
            align=0,  # left aligned
        )

        was_changed = True
        break  # Only process the first page where skills heading is found

    out = io.BytesIO()
    doc.save(out)
    doc.close()
    out.seek(0)
    return out.read(), was_changed, skills_text_before, skills_text_after
