#!/usr/bin/env python3
"""Test script to debug PDF bullet extraction."""

from pdf_utils import pdf_to_docx
from docx_utils import load_docx, collect_word_numbered_bullets
from docx import Document
import tempfile
import os

# Load the PDF
print("=" * 80)
print("TESTING PDF BULLET EXTRACTION")
print("=" * 80)
print()

pdf_path = "pdfres.pdf"
print(f"Loading PDF: {pdf_path}")

with open(pdf_path, 'rb') as f:
    pdf_bytes = f.read()

print(f"PDF size: {len(pdf_bytes)} bytes")
print()

# Convert to DOCX
print("Converting PDF to DOCX...")
try:
    docx_bytes = pdf_to_docx(pdf_bytes)
    print(f"✓ Conversion successful, DOCX size: {len(docx_bytes)} bytes")
except Exception as e:
    print(f"✗ Conversion failed: {e}")
    exit(1)

print()

# Save converted DOCX for inspection
debug_path = "pdfres_converted.docx"
with open(debug_path, 'wb') as f:
    f.write(docx_bytes)
print(f"Saved converted DOCX to: {debug_path}")
print()

# Load DOCX
doc = load_docx(docx_bytes)
print(f"Document has {len(doc.paragraphs)} paragraphs")
print()

# Show first 20 paragraphs
print("=" * 80)
print("FIRST 20 PARAGRAPHS:")
print("=" * 80)
for i, p in enumerate(doc.paragraphs[:20]):
    text = p.text.strip()
    if text:
        print(f"Para {i}: '{text[:100]}'")
        # Check if it has bullet formatting
        pPr = p._p.pPr
        has_numPr = pPr is not None and getattr(pPr, "numPr", None) is not None
        print(f"  -> has_numPr: {has_numPr}, first_char: {repr(text[0]) if text else 'N/A'}")
    else:
        print(f"Para {i}: (empty)")

print()

# Try standard bullet extraction
print("=" * 80)
print("STANDARD BULLET EXTRACTION (use_heuristics=False):")
print("=" * 80)
bullets_std, paras_std = collect_word_numbered_bullets(doc, use_heuristics=False)
print(f"Found {len(bullets_std)} bullets")
for i, bullet in enumerate(bullets_std[:5]):
    print(f"{i+1}. '{bullet[:100]}' (len={len(bullet)})")
print()

# Try heuristic bullet extraction
print("=" * 80)
print("HEURISTIC BULLET EXTRACTION (use_heuristics=True):")
print("=" * 80)
bullets_heur, paras_heur = collect_word_numbered_bullets(doc, use_heuristics=True)
print(f"Found {len(bullets_heur)} bullets")
for i, bullet in enumerate(bullets_heur[:10]):
    if bullet.strip():
        print(f"{i+1}. '{bullet[:150]}'")
    else:
        print(f"{i+1}. (EMPTY - len={len(bullet)}, repr={repr(bullet)})")
print()

# Check for empty bullets
empty_count = sum(1 for b in bullets_heur if not b.strip())
print(f"Empty bullets: {empty_count}/{len(bullets_heur)}")

if empty_count > 0:
    print()
    print("=" * 80)
    print("DEBUGGING EMPTY BULLETS:")
    print("=" * 80)
    for i, (bullet, para) in enumerate(zip(bullets_heur, paras_heur)):
        if not bullet.strip():
            print(f"\nEmpty bullet {i+1}:")
            print(f"  bullet value: {repr(bullet)}")
            print(f"  para.text: {repr(para.text[:100])}")
            print(f"  para.runs: {len(para.runs)}")
            if para.runs:
                print(f"  First run text: {repr(para.runs[0].text if para.runs else 'N/A')}")

print()
print("=" * 80)
print("You can inspect the converted DOCX at: " + debug_path)
print("=" * 80)
