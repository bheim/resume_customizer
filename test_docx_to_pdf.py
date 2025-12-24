#!/usr/bin/env python3
"""Test DOCX to PDF conversion."""

from pdf_utils import docx_to_pdf

# Test with the converted DOCX we already have
print("Testing DOCX to PDF conversion...")
print()

with open("pdfres_converted.docx", 'rb') as f:
    docx_bytes = f.read()

print(f"Input DOCX size: {len(docx_bytes)} bytes")

try:
    pdf_bytes = docx_to_pdf(docx_bytes)
    print(f"✓ Conversion successful!")
    print(f"Output PDF size: {len(pdf_bytes)} bytes")

    # Save for inspection
    with open("test_output.pdf", 'wb') as f:
        f.write(pdf_bytes)

    print()
    print("Saved output to: test_output.pdf")

except Exception as e:
    print(f"✗ Conversion failed: {e}")
    print()
    print("Note: This may require LibreOffice to be installed.")
    print("Install with: brew install libreoffice")
