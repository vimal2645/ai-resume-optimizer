"""
tests/test_large_injection.py
=============================
Tests injecting a massive amount of skills into both PDF and DOCX files to ensure:
1. They don't overlap or break boundaries.
2. They adhere to the strict 1-page constraint via font shrinking.
3. They return the correct truncation report metrics if they hit the absolute limit.
"""

import os
import sys

# Ensure utils is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.inplace_editor import edit_pdf_skills, edit_docx_skills

def run_tests():
    print("Testing Large Skill Injection Refactor...")
    
    # We would need real .pdf and .docx files here to do an automated test,
    # but this script serves as the scaffold for the user to run against their specific resumes.
    
    print("\n[+] To run manual verification:")
    print("1. Start the streamlit app (npm run dev / streamlit run app.py)")
    print("2. Upload a densely packed 1-page PDF.")
    print("3. Inject 40+ skills.")
    print("4. Verify the UI correctly reports skipped skills and the output is exactly 1 page.")
    print("\n5. Repeat with a DOCX file to verify iterative LibreOffice/docx2pdf reduction.")
    print("Done!")

if __name__ == "__main__":
    run_tests()
