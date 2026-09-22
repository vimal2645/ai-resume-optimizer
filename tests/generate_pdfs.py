"""
tests/generate_pdfs.py
======================
Helper script to generate test PDF fixtures using PyMuPDF.
LibreOffice/soffice has been removed; PDFs are now created directly.
"""
import os
import io
import sys

sys.path.insert(0, '.')

try:
    import pymupdf as fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

SAMPLE_RESUME_TEXT = '''
John Smith
john@example.com

Summary
Experienced engineer.

Technical Skills
Python, Django, FastAPI, PostgreSQL

Experience
Senior Software Engineer | TechCorp Ltd
January 2022 - Present
• Built a distributed microservices platform using Python
• Led a team of 4 engineers

Software Engineer | StartupXYZ
March 2020 - December 2021
• Developed Django backend
• Integrated AWS S3

Projects
Resume Optimizer Tool
• Built a skill extractor
• Deployed on Streamlit
'''

resume2 = """
Jane Doe
jane@example.com

Summary
Data Scientist with 3 years of experience.

Technical Skills
Python, SQL, Tableau, Pandas, Scikit-learn, Machine Learning

Experience
Data Scientist | DataCorp
March 2020 - Present
• Built predictive models using Python and Pandas
• Created dashboards in Tableau

Data Analyst | Analytics Inc
Jan 2018 - Feb 2020
• Wrote SQL queries
• Prepared reports
"""


def text_to_pdf(text: str) -> bytes:
    """Create a simple single-page PDF from plain text using PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page()
    y = 50
    for line in text.strip().splitlines():
        if y > 750:
            page = doc.new_page()
            y = 50
        page.insert_text((50, y), line, fontsize=11)
        y += 16
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


print('Generating PDF fixtures...')
os.makedirs('tests/pdfs', exist_ok=True)

if HAS_FITZ:
    pdf1 = text_to_pdf(SAMPLE_RESUME_TEXT)
    with open('tests/pdfs/resume1.pdf', 'wb') as f:
        f.write(pdf1)
    print('Written tests/pdfs/resume1.pdf')

    pdf2 = text_to_pdf(resume2)
    with open('tests/pdfs/resume2.pdf', 'wb') as f:
        f.write(pdf2)
    print('Written tests/pdfs/resume2.pdf')
else:
    print('PyMuPDF not installed — skipping PDF generation.')

print('Done.')
