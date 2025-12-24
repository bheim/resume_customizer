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
    Convert DOCX bytes to PDF bytes using pure Python (reportlab).

    This function parses the DOCX and generates a PDF directly without
    requiring any system dependencies like LibreOffice.

    Args:
        docx_bytes: Raw bytes of DOCX file

    Returns:
        bytes: Raw bytes of converted PDF file

    Raises:
        Exception: If conversion fails
    """
    from io import BytesIO
    from docx import Document
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

    try:
        log.info(f"Converting DOCX to PDF (input size: {len(docx_bytes)} bytes)")

        # Load DOCX
        doc = Document(BytesIO(docx_bytes))

        # Create PDF in memory
        pdf_buffer = BytesIO()
        pdf_doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )

        # Build PDF content
        styles = getSampleStyleSheet()
        story = []

        # Custom styles for different text types
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=11,
            leading=14,
            spaceAfter=6
        )

        bullet_style = ParagraphStyle(
            'CustomBullet',
            parent=styles['Normal'],
            fontSize=11,
            leading=14,
            leftIndent=20,
            spaceAfter=3,
            bulletIndent=10
        )

        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading1'],
            fontSize=14,
            leading=16,
            spaceAfter=8,
            spaceBefore=8,
            bold=True
        )

        # Process each paragraph
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                story.append(Spacer(1, 0.1*inch))
                continue

            # Determine if it's a heading (all caps or bold)
            is_heading = text.isupper() and len(text) > 2

            # Determine if it's a bullet
            is_bullet = text and text[0] in '•●◦-–—'

            # Build formatted text
            formatted_text = ""
            for run in para.runs:
                run_text = run.text
                if not run_text:
                    continue

                # Apply formatting
                if run.bold:
                    run_text = f"<b>{run_text}</b>"
                if run.italic:
                    run_text = f"<i>{run_text}</i>"
                if run.underline:
                    run_text = f"<u>{run_text}</u>"

                formatted_text += run_text

            # Escape any remaining XML special chars
            if not formatted_text:
                formatted_text = text

            # Add to story with appropriate style
            try:
                if is_heading:
                    story.append(Paragraph(formatted_text, heading_style))
                elif is_bullet:
                    # Remove bullet char and add proper bullet
                    bullet_text = formatted_text.lstrip('•●◦-–— ')
                    story.append(Paragraph(f"• {bullet_text}", bullet_style))
                else:
                    story.append(Paragraph(formatted_text, normal_style))
            except Exception as e:
                # Fallback to plain text if formatting fails
                log.warning(f"Formatting failed for paragraph, using plain text: {e}")
                story.append(Paragraph(text, normal_style))

        # Build PDF
        pdf_doc.build(story)
        pdf_bytes = pdf_buffer.getvalue()
        pdf_buffer.close()

        log.info(f"DOCX to PDF conversion successful (output size: {len(pdf_bytes)} bytes)")
        return pdf_bytes

    except Exception as e:
        log.exception(f"DOCX to PDF conversion failed: {e}")
        raise Exception(f"Failed to convert DOCX to PDF: {str(e)}")
