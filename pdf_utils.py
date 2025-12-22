"""PDF utility functions for converting between PDF and DOCX formats."""

import tempfile
import os
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
