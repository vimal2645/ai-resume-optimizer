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
        return file_bytes, False, "", "", {"added": 0, "skipped": 0, "skipped_names": [], "reason": "No changes made."}

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
        return file_bytes, False, "", "", {"added": 0, "skipped": 0, "skipped_names": [], "reason": "No changes made."}

    if not skills_para_indices:
        return file_bytes, False, "", "", {"added": 0, "skipped": 0, "skipped_names": [], "reason": "No changes made."}

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
        return file_bytes, False, original_text, original_text, {"added": 0, "skipped": 0, "skipped_names": [], "reason": "No changes made."}

    # ── Detect separator style from existing text ─────────────────────────
    separator = ", "
    if ";" in original_text:
        separator = "; "
    elif " | " in original_text:
        separator = " | "

    # ── Append to the last run of the target paragraph ────────────────────
    skills_text_before = original_text.strip()
    addition = separator + separator.join(new_skills)

    # ── Iterative 1-Page Fitting ──────────────────────────────────────────────
    from docx.shared import Pt
    import fitz
    from utils.converter import convert_docx_to_pdf
    import copy

    if not target_para.runs:
        target_para.add_run()
    
    # Try to find original font size, default to 11
    start_pt = 11.0
    for r in target_para.runs:
        if r.font.size is not None:
            start_pt = r.font.size.pt
            break
            
    current_pt = start_pt
    final_skills = list(new_skills)
    skipped_skills = []
    
    while True:
        # Clone doc to test this iteration
        test_out = io.BytesIO()
        doc.save(test_out)
        test_out.seek(0)
        
        test_doc = docx.Document(test_out)
        test_para = test_doc.paragraphs[target_idx]
        
        addition = separator + separator.join(final_skills)
        target_run = test_para.runs[-1]
        target_run.text += addition
        target_run.font.size = Pt(current_pt)
        
        # Save to bytes for conversion
        iter_out = io.BytesIO()
        test_doc.save(iter_out)
        iter_out.seek(0)
        iter_bytes = iter_out.read()
        
        # Check PDF page count
        try:
            pdf_bytes = convert_docx_to_pdf(iter_bytes)
            pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = pdf_doc.page_count
            pdf_doc.close()
        except Exception:
            # If conversion fails in environment, we cannot enforce 1-page. Just accept it.
            page_count = 1
            
        if page_count == 1:
            # It fits! Apply to the real doc
            real_run = target_para.runs[-1]
            real_run.text += addition
            real_run.font.size = Pt(current_pt)
            break
            
        # It overflowed to page 2.
        if current_pt > 8.0:
            current_pt -= 0.5
        else:
            # Truncate one skill and keep trying at 8.0pt
            if final_skills:
                skipped_skills.append(final_skills.pop())
            else:
                break
                
    skills_text_after = target_para.text.strip()
    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    
    results = {
        "added": len(new_skills) - len(skipped_skills),
        "skipped": len(skipped_skills),
        "skipped_names": skipped_skills,
        "reason": "DOCX 1-page limit reached" if skipped_skills else ""
    }
    
    return out.read(), True, skills_text_before, skills_text_after, results


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
        return file_bytes, False, "", "", {"added": 0, "skipped": 0, "skipped_names": [], "reason": "No changes made."}

    try:
        import pymupdf as fitz  # PyMuPDF
    except ImportError:
        # PyMuPDF not installed — return original unchanged
        return file_bytes, False, "", "", {"added": 0, "skipped": 0, "skipped_names": [], "reason": "No changes made."}

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
        skills_blocks = []
        next_block_y0 = None

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
                
            # If the block is actually the NEXT section heading, we stop collecting!
            if re.match(
                r"^(experience|education|projects|certifications|summary|"
                r"objective|profile|achievements|awards|publications|"
                r"professional experience|work experience)\s*:?\s*$",
                btext,
                re.IGNORECASE,
            ):
                next_block_y0 = by0
                break

            skills_blocks.append(block)
            
        if not skills_blocks and next_block_y0 is None:
            continue
            
        if not skills_blocks and next_block_y0 is not None:
            # The skills section is completely blank. We will create a new block!
            bx0 = heading_rect.x0
            by0 = heading_rect.y1 + 2
            bx1 = heading_rect.x1
            by1 = by0 + 10 # dummy initial height
            original_skills_text = ""
            skills_text_before = ""
        else:
            bx0 = min([b[0] for b in skills_blocks])
            by0 = min([b[1] for b in skills_blocks])
            bx1 = max([b[2] for b in skills_blocks])
            by1 = max([b[3] for b in skills_blocks])
            # Concatenate all text in the blocks, replacing internal newlines with spaces
            original_skills_text = " ".join([b[4].strip().replace('\n', ' ') for b in skills_blocks])
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

        if original_skills_text:
            updated_text = original_skills_text.rstrip() + separator + separator.join(new_skills)
        else:
            updated_text = separator.join(new_skills)
            
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
                            # Prevent invisible/unreadable text (e.g. white or light grey on white background)
                            if sum(text_color) > 2.0:
                                text_color = (0, 0, 0)
                        break
                    break
                break
        except Exception:
            pass

        # Find the next block's top boundary to know how much vertical space we have
        if next_block_y0 is not None:
            # Leave a 5px buffer above the next section heading
            max_bottom = next_block_y0 - 5
        else:
            # If there is no next section (skills is at the very bottom), use page margin
            max_bottom = page.rect.height - 30
            
        # Give it at least some minimum height
        max_bottom = max(max_bottom, by1 + 15)

        # ── Redact (white-box) the existing skills blocks ───────────────────
        if skills_blocks:
            for b in skills_blocks:
                redact_rect = fitz.Rect(b[0], b[1], b[2], b[3])
                page.add_redact_annot(redact_rect, fill=(1, 1, 1))
            page.apply_redactions()

        # ── Re-draw the updated skills text ───────────────────────────────
        right_margin = page.rect.width - 30 # default 30px right margin
        right_boundary = max(right_margin, bx1) if bx1 > bx0 else right_margin
        
        textbox_rect = fitz.Rect(bx0, by0, right_boundary, max_bottom)
        # ── Calculate exact height needed, shrink font, or truncate ──
        all_blocks = page.get_text("blocks")
        bottom_original_lowest_y = max([b[3] for b in all_blocks if b[4].strip()] + [by1])
        available_height = max_bottom - by0
        max_allowed_needed_height = max(available_height, page.rect.height - 20 - bottom_original_lowest_y + available_height)
        
        current_fontsize = font_size
        final_fontsize = font_size
        final_text = wrapped_text
        needed_height = 0
        
        while current_fontsize >= 8.0:
            dummy_doc = fitz.open()
            dummy_page = dummy_doc.new_page(width=page.rect.width, height=10000)
            test_rect = fitz.Rect(bx0, by0, right_boundary, 10000)
            res_height = dummy_page.insert_textbox(
                test_rect,
                wrapped_text,
                fontname=font_name,
                fontsize=current_fontsize,
                align=0
            )
            dummy_doc.close()
            needed_height = test_rect.height - res_height + 5
            
            if needed_height <= max_allowed_needed_height:
                final_fontsize = current_fontsize
                break
            current_fontsize -= 0.5
            
        # If it still overflows at 8.0pt, we truncate
        if needed_height > max_allowed_needed_height:
            final_fontsize = 8.0
            words = wrapped_text.split(separator)
            while len(words) > 0:
                current_text = separator.join(words).strip()
                if len(words) < len(wrapped_text.split(separator)):
                    current_text += "..."
                    
                dummy_doc = fitz.open()
                dummy_page = dummy_doc.new_page(width=page.rect.width, height=10000)
                test_rect = fitz.Rect(bx0, by0, right_boundary, 10000)
                res_height = dummy_page.insert_textbox(
                    test_rect,
                    current_text,
                    fontname=font_name,
                    fontsize=8.0,
                    align=0
                )
                dummy_doc.close()
                needed_height = test_rect.height - res_height + 5
                
                if needed_height <= max_allowed_needed_height:
                    final_text = current_text
                    break
                words.pop()
        
        shift_amount = 0
        if needed_height > available_height:
            shift_amount = needed_height - available_height
            
        # ── Redact (white-box) the existing skills blocks ──
        if skills_blocks:
            for b in skills_blocks:
                redact_rect = fitz.Rect(b[0], b[1], b[2], b[3])
                page.add_redact_annot(redact_rect, fill=(1, 1, 1))
            page.apply_redactions()

        # ── Shift and Draw ──
        if shift_amount > 0 and next_block_y0 is not None:
            split_y = max_bottom
            
            new_doc = fitz.open()
            new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
            
            # Draw top half
            top_clip = fitz.Rect(0, 0, page.rect.width, split_y)
            new_page.show_pdf_page(top_clip, doc, 0, clip=top_clip)
            
            # Draw bottom half shifted down
            bottom_clip = fitz.Rect(0, split_y, page.rect.width, page.rect.height)
            bottom_target = fitz.Rect(0, split_y + shift_amount, page.rect.width, page.rect.height + shift_amount)
            new_page.show_pdf_page(bottom_target, doc, 0, clip=bottom_clip)
            
            # Draw the skills text in the new gap
            textbox_rect = fitz.Rect(bx0, by0, right_boundary, by0 + needed_height)
            new_page.insert_textbox(
                textbox_rect,
                final_text,
                fontname=font_name,
                fontsize=final_fontsize,
                color=text_color,
                align=0
            )
            
            doc = new_doc
            was_changed = True
            break
            
        else:
            # Fits perfectly in the existing gap!
            textbox_rect = fitz.Rect(bx0, by0, right_boundary, by0 + needed_height if needed_height < available_height else max_bottom)
            page.insert_textbox(
                textbox_rect,
                final_text,
                fontname=font_name,
                fontsize=final_fontsize,
                color=text_color,
                align=0
            )
            was_changed = True
            break

    out = io.BytesIO()
    doc.save(out)
    doc.close()
    out.seek(0)
    
    skipped_names = [s for s in optimizable_skills if s.lower() not in final_text.lower()]
    results = {
        "added": len(optimizable_skills) - len(skipped_names),
        "skipped": len(skipped_names),
        "skipped_names": skipped_names,
        "reason": "Page overflow at minimum font size" if skipped_names else ""
    }
    
    return out.read(), was_changed, skills_text_before, final_text, results
