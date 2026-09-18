"""
tests/test_inplace_edit.py
==========================
Four automated tests verifying the in-place edit model.

Test 1 — OPTIMIZABLE skill promotion (DOCX)
    MongoDB is in a project bullet but absent from the Skills section.
    JD requires MongoDB.  After editing, the Skills section includes
    MongoDB and every other paragraph is byte-identical to the original.

Test 2 — GENUINELY_MISSING skill isolation
    Kubernetes appears nowhere in the resume.  JD requires Kubernetes.
    Kubernetes must NOT appear in the output document.  It should only
    appear in the genuinely_missing bucket.

Test 3 — Format preservation
    DOCX upload → DOCX output.
    Synthetic PDF upload → PDF output.
    Both open without error after editing.

Test 4 — No forbidden references anywhere in the codebase
    No files reference torch, sentence_transformers, soffice, or pdfinfo.
"""

import io
import os
import sys
import glob
import pytest

# Ensure the project root is on the path when running from tests/
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ---------------------------------------------------------------------------
# Helpers: minimal DOCX builder
# ---------------------------------------------------------------------------

def _make_test_docx(
    skills_line: str = "Python, Django, PostgreSQL",
    project_text: str = "Built a REST API using MongoDB for data persistence.",
    skills_heading: str = "Technical Skills",
) -> bytes:
    """
    Build a minimal DOCX in memory with:
      - A heading paragraph: skills_heading
      - A skills content paragraph: skills_line
      - An experience heading + a project bullet containing project_text
    """
    from docx import Document
    from docx.shared import Pt

    doc = Document()

    # Candidate name
    doc.add_paragraph("Jane Developer")

    # Skills section
    h = doc.add_paragraph(skills_heading)
    for run in h.runs:
        run.bold = True
    doc.add_paragraph(skills_line)

    # Experience section
    exp_h = doc.add_paragraph("Experience")
    for run in exp_h.runs:
        run.bold = True
    doc.add_paragraph("Senior Developer | Acme Corp | 2021–Present")
    doc.add_paragraph(f"• {project_text}")

    # Education (must remain untouched)
    edu_h = doc.add_paragraph("Education")
    for run in edu_h.runs:
        run.bold = True
    doc.add_paragraph("B.Sc. Computer Science | State University | 2018")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_test_pdf(
    skills_line: str = "Python, Django, PostgreSQL",
    project_text: str = "Built a REST API using MongoDB for data persistence.",
) -> bytes:
    """
    Build a minimal single-page PDF in memory using PyMuPDF (reportlab-free).
    Returns None if PyMuPDF is not installed (Test 3 PDF sub-test is skipped).
    """
    try:
        import fitz
    except ImportError:
        return None

    doc = fitz.open()
    page = doc.new_page()

    y = 50
    page.insert_text((50, y), "Jane Developer", fontsize=14)
    y += 30

    page.insert_text((50, y), "Technical Skills", fontsize=12, fontname="helv")
    y += 18
    page.insert_text((50, y), skills_line, fontsize=10)
    y += 25

    page.insert_text((50, y), "Experience", fontsize=12, fontname="helv")
    y += 18
    page.insert_text((50, y), "Senior Developer | Acme Corp | 2021–Present", fontsize=10)
    y += 15
    page.insert_text((50, y), f"• {project_text}", fontsize=10)
    y += 25

    page.insert_text((50, y), "Education", fontsize=12, fontname="helv")
    y += 18
    page.insert_text((50, y), "B.Sc. Computer Science | State University | 2018", fontsize=10)

    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Helpers: text extraction from output files
# ---------------------------------------------------------------------------

def _docx_paragraphs(file_bytes: bytes) -> list:
    """Return list of (text, bold) for all paragraphs in a DOCX."""
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    return [p.text for p in doc.paragraphs]


def _pdf_full_text(file_bytes: bytes) -> str:
    """Return full text of a PDF using pypdf."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(file_bytes))
    parts = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            parts.append(t)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Test 1 — OPTIMIZABLE skill promotion (DOCX)
# ---------------------------------------------------------------------------

class TestOptimizablePromotion:

    def test_mongodb_added_to_skills_section(self):
        """
        MongoDB is in a project bullet.  JD requires MongoDB.
        After in-place edit the Skills paragraph must contain 'MongoDB'.
        """
        from utils.inplace_editor import edit_docx_skills

        original_bytes = _make_test_docx(
            skills_line="Python, Django, PostgreSQL",
            project_text="Built a REST API using MongoDB for data persistence.",
        )

        optimizable = ["MongoDB"]
        out_bytes, was_changed, before, after = edit_docx_skills(
            original_bytes, optimizable
        )

        assert was_changed, "was_changed should be True when skills are added"
        assert "MongoDB" in after, f"'MongoDB' should appear in the updated skills text; got: {after!r}"
        assert "MongoDB" not in before, f"'MongoDB' should NOT be in before text; got: {before!r}"

    def test_non_skills_paragraphs_unchanged(self):
        """
        After editing, every paragraph except the skills content paragraph
        must be byte-identical (same text) to the original.
        """
        from utils.inplace_editor import edit_docx_skills

        original_bytes = _make_test_docx(
            skills_line="Python, Django, PostgreSQL",
            project_text="Built a REST API using MongoDB for data persistence.",
        )
        original_paras = _docx_paragraphs(original_bytes)

        optimizable = ["MongoDB"]
        out_bytes, was_changed, before, after = edit_docx_skills(
            original_bytes, optimizable
        )
        out_paras = _docx_paragraphs(out_bytes)

        # Same paragraph count
        assert len(original_paras) == len(out_paras), (
            f"Paragraph count changed: {len(original_paras)} → {len(out_paras)}"
        )

        # Find which paragraph changed
        changed_indices = [
            i for i, (o, n) in enumerate(zip(original_paras, out_paras)) if o != n
        ]

        # Exactly one paragraph should have changed (the skills content para)
        assert len(changed_indices) == 1, (
            f"Expected exactly 1 changed paragraph, got {len(changed_indices)}: "
            f"indices={changed_indices}\n"
            f"Original: {original_paras}\n"
            f"Output:   {out_paras}"
        )

        changed_idx = changed_indices[0]
        assert "Python" in out_paras[changed_idx], (
            f"Changed paragraph should still contain original skills; got: {out_paras[changed_idx]!r}"
        )
        assert "MongoDB" in out_paras[changed_idx], (
            f"Changed paragraph should contain MongoDB; got: {out_paras[changed_idx]!r}"
        )

        # All other paragraphs must be identical
        for i, (orig, out) in enumerate(zip(original_paras, out_paras)):
            if i != changed_idx:
                assert orig == out, (
                    f"Paragraph {i} changed unexpectedly:\n"
                    f"  original: {orig!r}\n"
                    f"  output:   {out!r}"
                )

    def test_no_duplicate_skills(self):
        """Skills already in the Skills line are not duplicated."""
        from utils.inplace_editor import edit_docx_skills

        original_bytes = _make_test_docx(skills_line="Python, Django, PostgreSQL, MongoDB")
        optimizable = ["MongoDB"]
        out_bytes, was_changed, before, after = edit_docx_skills(
            original_bytes, optimizable
        )
        # MongoDB already present — nothing should change
        assert not was_changed, "was_changed should be False when skill already listed"
        assert after == "" or "MongoDB" not in after.replace(before, ""), (
            "No new MongoDB should have been appended"
        )


# ---------------------------------------------------------------------------
# Test 2 — GENUINELY_MISSING skill isolation
# ---------------------------------------------------------------------------

class TestGenuinelyMissing:

    def test_kubernetes_not_in_resume_anywhere(self):
        """
        Kubernetes is absent from the full resume text.
        After classify_skills it must be in genuinely_missing, not optimizable.
        """
        from core.parser import classify_skills

        skills_full = ["Python", "Django", "PostgreSQL", "MongoDB"]
        skills_in_section = ["Python", "Django", "PostgreSQL"]
        jd_skills = ["Python", "MongoDB", "Kubernetes"]

        buckets = classify_skills(
            jd_skills=jd_skills,
            skills_full=skills_full,
            skills_in_skills_section=skills_in_section,
        )

        assert "Kubernetes" in buckets["genuinely_missing"], (
            f"Kubernetes should be genuinely_missing; got buckets={buckets}"
        )
        assert "Kubernetes" not in buckets["already_listed"], (
            "Kubernetes must NOT be in already_listed"
        )
        assert "Kubernetes" not in buckets["optimizable"], (
            "Kubernetes must NOT be in optimizable"
        )

    def test_kubernetes_not_written_to_docx(self):
        """
        Even if someone mistakenly passes Kubernetes as optimizable (it
        shouldn't be — but belt-and-suspenders), edit_docx_skills only
        deduplicates from the skills section text.  The stronger guarantee
        is that classify_skills puts it in genuinely_missing (tested above).
        This test confirms a DOCX with no Kubernetes text at all does not
        gain Kubernetes in its output when optimizable=[] (correct pipeline).
        """
        from utils.inplace_editor import edit_docx_skills

        original_bytes = _make_test_docx(
            skills_line="Python, Django, PostgreSQL",
            project_text="Built a REST API using Django for data persistence.",  # no Kubernetes
        )

        # Correct pipeline: genuinely_missing → optimizable=[]
        out_bytes, was_changed, _, _ = edit_docx_skills(original_bytes, [])

        assert not was_changed
        full_text = "\n".join(_docx_paragraphs(out_bytes))
        assert "Kubernetes" not in full_text, (
            f"Kubernetes must not appear anywhere in the output document; text: {full_text!r}"
        )


# ---------------------------------------------------------------------------
# Test 3 — Format preservation
# ---------------------------------------------------------------------------

class TestFormatPreservation:

    def test_docx_in_docx_out(self):
        """
        DOCX upload → DOCX output.  Output must open without error.
        """
        from utils.inplace_editor import edit_docx_skills
        from docx import Document

        original_bytes = _make_test_docx()
        out_bytes, _, _, _ = edit_docx_skills(original_bytes, ["MongoDB"])

        # Must be parseable as a DOCX
        doc = Document(io.BytesIO(out_bytes))
        assert len(doc.paragraphs) > 0, "Output DOCX has no paragraphs"

    def test_pdf_in_pdf_out(self):
        """
        Synthetic PDF upload → PDF output.  Output must be readable as PDF.
        """
        pytest.importorskip("fitz", reason="PyMuPDF not installed — skipping PDF test")
        from utils.inplace_editor import edit_pdf_skills
        from pypdf import PdfReader

        pdf_bytes = _make_test_pdf()
        if pdf_bytes is None:
            pytest.skip("Could not build test PDF (PyMuPDF not available)")

        out_bytes, _, _, _ = edit_pdf_skills(pdf_bytes, ["MongoDB"])

        # Must be parseable as a PDF
        reader = PdfReader(io.BytesIO(out_bytes))
        assert len(reader.pages) >= 1, "Output PDF has no pages"

    def test_docx_output_not_pdf(self):
        """DOCX input must not produce PDF output bytes (magic number check)."""
        from utils.inplace_editor import edit_docx_skills

        original_bytes = _make_test_docx()
        out_bytes, _, _, _ = edit_docx_skills(original_bytes, ["MongoDB"])

        # DOCX files are ZIP archives starting with PK\x03\x04
        assert out_bytes[:4] == b"PK\x03\x04", (
            "Output is not a valid DOCX/ZIP archive"
        )

    def test_pdf_output_not_docx(self):
        """PDF input must not produce DOCX output bytes (magic number check)."""
        pytest.importorskip("fitz", reason="PyMuPDF not installed — skipping PDF test")
        from utils.inplace_editor import edit_pdf_skills

        pdf_bytes = _make_test_pdf()
        if pdf_bytes is None:
            pytest.skip("Could not build test PDF")

        out_bytes, _, _, _ = edit_pdf_skills(pdf_bytes, ["MongoDB"])

        # PDF files start with %PDF
        assert out_bytes[:4] == b"%PDF", (
            "Output is not a valid PDF file"
        )


# ---------------------------------------------------------------------------
# Test 4 — No forbidden references in codebase
# ---------------------------------------------------------------------------

class TestForbiddenReferences:

    def _all_py_files(self) -> list:
        """Return all .py files under the project root."""
        pattern = os.path.join(_ROOT, "**", "*.py")
        return glob.glob(pattern, recursive=True)

    def _search_imports_and_calls(self, token: str) -> list:
        """
        Return (filepath, lineno, line) where token appears as a code-level
        import or call (not in comments or docstrings).
        We identify comments by # prefix after stripping and docstrings by
        triple-quote context — a simpler heuristic: if the line stripped starts
        with # or the token is only inside a string literal, skip it.
        """
        hits = []
        for path in self._all_py_files():
            if os.path.basename(path) == "test_inplace_edit.py":
                continue  # skip the test file itself
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    in_docstring = False
                    docstring_char = None
                    for lineno, raw_line in enumerate(f, start=1):
                        line = raw_line.rstrip()
                        stripped = line.lstrip()

                        # Track triple-quote docstring blocks
                        for q in ('"""', "'''"):
                            count = raw_line.count(q)
                            if not in_docstring and count % 2 == 1:
                                in_docstring = True
                                docstring_char = q
                            elif in_docstring and q == docstring_char and count % 2 == 1:
                                in_docstring = False
                                docstring_char = None

                        if in_docstring:
                            continue
                        # Skip pure comment lines
                        if stripped.startswith("#"):
                            continue
                        # Skip lines that don't contain the token
                        if token not in line:
                            continue
                        # Strip inline comment from the code portion
                        code_part = line.split("#")[0]
                        if token in code_part:
                            hits.append((path, lineno, line.strip()))
            except Exception:
                pass
        return hits

    def test_no_sentence_transformers(self):
        """No source file should import or call sentence_transformers."""
        hits = self._search_imports_and_calls("sentence_transformers")
        hits += self._search_imports_and_calls("sentence-transformers")
        assert not hits, (
            "Found sentence_transformers reference(s):\n" +
            "\n".join(f"  {p}:{n}  {l}" for p, n, l in hits)
        )

    def test_no_torch(self):
        """No source file should import torch."""
        import_hits = [
            h for h in self._search_imports_and_calls("torch")
            if re.search(r"\b(import torch|from torch\b)", h[2])
        ]
        assert not import_hits, (
            "Found torch import reference(s):\n" +
            "\n".join(f"  {p}:{n}  {l}" for p, n, l in import_hits)
        )

    def test_no_soffice(self):
        """No source file should call soffice (LibreOffice)."""
        hits = self._search_imports_and_calls("soffice")
        assert not hits, (
            "Found soffice reference(s):\n" +
            "\n".join(f"  {p}:{n}  {l}" for p, n, l in hits)
        )

    def test_no_pdfinfo(self):
        """No source file should call pdfinfo."""
        hits = self._search_imports_and_calls("pdfinfo")
        assert not hits, (
            "Found pdfinfo reference(s):\n" +
            "\n".join(f"  {p}:{n}  {l}" for p, n, l in hits)
        )
