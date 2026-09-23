"""
utils/converter.py
==================
Handles converting DOCX bytes to PDF bytes using local tools (docx2pdf or LibreOffice).
"""

import os
import tempfile
import subprocess
import platform

def convert_docx_to_pdf(docx_bytes: bytes) -> bytes:
    """
    Converts a DOCX file in memory to a PDF file in memory.
    Uses docx2pdf on Windows (requires MS Word), or LibreOffice on Linux.
    Raises Exception if conversion fails.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as docx_file:
        docx_file.write(docx_bytes)
        docx_path = docx_file.name

    pdf_path = docx_path.replace(".docx", ".pdf")
    
    try:
        if platform.system() == "Windows":
            try:
                from docx2pdf import convert
                convert(docx_path, pdf_path)
            except Exception as e:
                # Fallback to libreoffice on Windows if docx2pdf fails
                try:
                    subprocess.run(
                        ["soffice", "--headless", "--convert-to", "pdf", docx_path, "--outdir", os.path.dirname(docx_path)],
                        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                except FileNotFoundError:
                    raise Exception("PDF conversion failed. You must have Microsoft Word or LibreOffice installed on Windows.") from e
                except subprocess.CalledProcessError as sub_e:
                    raise Exception(f"LibreOffice conversion failed: {sub_e.stderr.decode()}") from e
        else:
            # Linux / macOS (Streamlit Cloud uses LibreOffice via packages.txt)
            try:
                subprocess.run(
                    ["libreoffice", "--headless", "--convert-to", "pdf", docx_path, "--outdir", os.path.dirname(docx_path)],
                    check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
            except FileNotFoundError as e:
                raise Exception("LibreOffice not found. Make sure 'libreoffice' is in packages.txt.") from e
            except subprocess.CalledProcessError as e:
                raise Exception(f"LibreOffice conversion failed: {e.stderr.decode()}") from e
                
        # Read the generated PDF
        if not os.path.exists(pdf_path):
            raise Exception("PDF file was not created by the conversion tool.")
            
        with open(pdf_path, "rb") as pdf_file:
            pdf_bytes = pdf_file.read()
            
        return pdf_bytes
        
    finally:
        # Cleanup temp files
        if os.path.exists(docx_path):
            try:
                os.remove(docx_path)
            except:
                pass
        if os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except:
                pass
