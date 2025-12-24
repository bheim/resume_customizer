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
    Convert DOCX bytes to PDF bytes.

    Uses LibreOffice headless mode for conversion on Mac/Linux.
    Falls back to docx2pdf library on Windows.

    Args:
        docx_bytes: Raw bytes of DOCX file

    Returns:
        bytes: Raw bytes of converted PDF file

    Raises:
        Exception: If conversion fails or LibreOffice is not installed
    """
    docx_temp = None
    pdf_temp = None
    temp_dir = None

    try:
        # Create temporary directory for conversion
        temp_dir = tempfile.mkdtemp()

        # Save DOCX to temp file
        docx_temp = os.path.join(temp_dir, "input.docx")
        with open(docx_temp, 'wb') as f:
            f.write(docx_bytes)

        log.info(f"Converting DOCX to PDF (input size: {len(docx_bytes)} bytes)")

        # Try LibreOffice first (works on Mac/Linux)
        pdf_temp = os.path.join(temp_dir, "input.pdf")

        # Try to find LibreOffice/soffice executable
        soffice_paths = [
            '/Applications/LibreOffice.app/Contents/MacOS/soffice',  # Mac
            '/usr/bin/soffice',  # Linux
            '/usr/bin/libreoffice',  # Linux alternative
        ]

        soffice_cmd = None

        # Check explicit paths first
        for path in soffice_paths:
            if os.path.exists(path):
                soffice_cmd = path
                break

        # If not found, check if it's in PATH
        if not soffice_cmd:
            import shutil
            for cmd in ['soffice', 'libreoffice']:
                if shutil.which(cmd):
                    soffice_cmd = cmd
                    break

        if soffice_cmd:
            # Use LibreOffice headless conversion
            cmd = [
                soffice_cmd,
                '--headless',
                '--convert-to', 'pdf',
                '--outdir', temp_dir,
                docx_temp
            ]

            log.info(f"Using LibreOffice: {soffice_cmd}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                log.error(f"LibreOffice conversion failed: {result.stderr}")
                raise Exception(f"LibreOffice conversion failed: {result.stderr}")

            # Read the generated PDF
            if not os.path.exists(pdf_temp):
                raise Exception("PDF file was not created by LibreOffice")

            with open(pdf_temp, 'rb') as f:
                pdf_bytes = f.read()

            log.info(f"DOCX to PDF conversion successful (output size: {len(pdf_bytes)} bytes)")
            return pdf_bytes

        else:
            # LibreOffice not found, try docx2pdf library as fallback
            log.info("LibreOffice not found, trying docx2pdf library")
            try:
                from docx2pdf import convert

                pdf_output = os.path.join(temp_dir, "output.pdf")
                convert(docx_temp, pdf_output)

                with open(pdf_output, 'rb') as f:
                    pdf_bytes = f.read()

                log.info(f"DOCX to PDF conversion via docx2pdf successful (output size: {len(pdf_bytes)} bytes)")
                return pdf_bytes

            except Exception as e:
                log.exception(f"docx2pdf conversion failed: {e}")
                raise Exception(
                    "PDF conversion requires LibreOffice to be installed. "
                    "Install it with: brew install libreoffice (Mac) or apt-get install libreoffice (Linux)"
                )

    except subprocess.TimeoutExpired:
        log.error("DOCX to PDF conversion timed out")
        raise Exception("PDF conversion timed out after 30 seconds")

    except Exception as e:
        log.exception(f"DOCX to PDF conversion failed: {e}")
        raise Exception(f"Failed to convert DOCX to PDF: {str(e)}")

    finally:
        # Cleanup temp files
        if temp_dir and os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
