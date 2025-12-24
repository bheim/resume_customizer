"""PDF utility functions for converting between PDF and DOCX formats."""

import tempfile
import os
import subprocess
from typing import Tuple
from pdf2docx import Converter
from config import log


def pdf_to_docx(pdf_bytes: bytes, save_debug: bool = False) -> bytes:
    """
    Convert PDF bytes to DOCX bytes.

    Uses pdf2docx library to convert PDF to editable DOCX format.
    This allows us to process PDF resumes through our existing DOCX pipeline.

    Args:
        pdf_bytes: Raw bytes of PDF file

    Returns:
        bytes: Raw bytes of converted DOCX file

    Raises:
        Exception: If conversion fails
    """
    pdf_temp = None
    docx_temp = None

    try:
        # Create temporary files for conversion
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as pdf_tmp:
            pdf_tmp.write(pdf_bytes)
            pdf_temp = pdf_tmp.name

        # Create temp path for output DOCX
        docx_temp = pdf_temp.replace(".pdf", ".docx")

        # Convert PDF to DOCX
        log.info(f"Converting PDF to DOCX (input size: {len(pdf_bytes)} bytes)")
        cv = Converter(pdf_temp)
        cv.convert(docx_temp)
        cv.close()

        # Read converted DOCX
        with open(docx_temp, 'rb') as f:
            docx_bytes = f.read()

        log.info(f"PDF conversion successful (output size: {len(docx_bytes)} bytes)")
        return docx_bytes

    except Exception as e:
        log.exception(f"PDF to DOCX conversion failed: {e}")
        raise Exception(f"Failed to convert PDF to DOCX: {str(e)}")

    finally:
        # Cleanup temp files
        if pdf_temp and os.path.exists(pdf_temp):
            os.unlink(pdf_temp)
        if docx_temp and os.path.exists(docx_temp):
            os.unlink(docx_temp)


def is_pdf(content_type: str, file_bytes: bytes) -> bool:
    """
    Check if a file is a PDF.

    Args:
        content_type: MIME type from upload
        file_bytes: First few bytes of file for magic number check

    Returns:
        bool: True if file is a PDF
    """
    # Check content type
    if content_type == "application/pdf":
        return True

    # Check magic number (PDF files start with %PDF)
    if file_bytes[:4] == b'%PDF':
        return True

    return False


def is_docx(content_type: str, file_bytes: bytes) -> bool:
    """
    Check if a file is a DOCX.

    Args:
        content_type: MIME type from upload
        file_bytes: First few bytes of file for magic number check

    Returns:
        bool: True if file is a DOCX
    """
    # Check content type
    if content_type in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
        "application/msword"
    }:
        return True

    # Check magic number (DOCX files are ZIP files, start with PK)
    if file_bytes[:2] == b'PK':
        return True

    return False


def docx_to_pdf(docx_bytes: bytes) -> bytes:
    """
    Convert DOCX bytes to PDF bytes preserving formatting.

    Uses mammoth (DOCX→HTML) + weasyprint (HTML→PDF) to maintain
    the original document formatting, layout, fonts, and styling.

    Args:
        docx_bytes: Raw bytes of DOCX file

    Returns:
        bytes: Raw bytes of converted PDF file

    Raises:
        Exception: If conversion fails
    """
    from io import BytesIO
    import mammoth
    from weasyprint import HTML, CSS

    try:
        log.info(f"Converting DOCX to PDF (input size: {len(docx_bytes)} bytes)")

        # Step 1: Convert DOCX to HTML using mammoth (preserves formatting)
        result = mammoth.convert_to_html(BytesIO(docx_bytes))
        html_content = result.value

        # Log any conversion messages/warnings
        if result.messages:
            for msg in result.messages:
                log.debug(f"Mammoth: {msg}")

        # Step 2: Wrap HTML in a complete document with CSS for better rendering
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                @page {{
                    size: letter;
                    margin: 0.75in;
                }}
                body {{
                    font-family: Arial, Helvetica, sans-serif;
                    font-size: 11pt;
                    line-height: 1.4;
                    color: #000000;
                }}
                p {{
                    margin: 0 0 0.5em 0;
                }}
                ul, ol {{
                    margin: 0.5em 0;
                    padding-left: 1.5em;
                }}
                li {{
                    margin-bottom: 0.3em;
                }}
                strong {{
                    font-weight: bold;
                }}
                em {{
                    font-style: italic;
                }}
                h1, h2, h3, h4, h5, h6 {{
                    font-weight: bold;
                    margin: 0.5em 0 0.3em 0;
                }}
                h1 {{ font-size: 16pt; }}
                h2 {{ font-size: 14pt; }}
                h3 {{ font-size: 12pt; }}
                a {{
                    color: #0066cc;
                    text-decoration: underline;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """

        # Step 3: Convert HTML to PDF using weasyprint
        html = HTML(string=full_html)
        pdf_bytes = html.write_pdf()

        log.info(f"DOCX to PDF conversion successful (output size: {len(pdf_bytes)} bytes)")
        return pdf_bytes

    except Exception as e:
        log.exception(f"DOCX to PDF conversion failed: {e}")
        raise Exception(f"Failed to convert DOCX to PDF: {str(e)}")
