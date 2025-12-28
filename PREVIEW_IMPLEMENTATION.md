# Document Preview Implementation Guide (Client-Side DOCX Rendering)

## Overview

The preview uses **client-side DOCX rendering** with the `docx-preview` library to provide pixel-perfect accuracy. This approach ensures:
- ✅ Exact formatting match with downloaded DOCX
- ✅ Accurate page break detection (critical for resumes)
- ✅ True representation of spacing, fonts, and layout
- ⚠️ Requires CSS fixes for bullet rendering

**Why client-side DOCX rendering?**
For resumes, a small text difference can cause a page break issue (1 page vs 2 pages). HTML conversion loses fidelity and cannot accurately predict where DOCX page breaks occur. Client-side DOCX rendering shows the exact document that will be downloaded.

## Backend: `/v2/preview` Endpoint

**What it does:**
1. Accepts same parameters as `/download` (bullets, user_id, session_id, or file upload)
2. Generates DOCX with enhanced bullets (same logic as download)
3. Returns DOCX bytes with MIME type `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
4. Falls back to base resume if session not found (graceful degradation)

**Already implemented!** No backend changes needed.

**Key difference from `/download`:**
- `/download` includes `Content-Disposition: attachment` header to trigger download
- `/v2/preview` omits this header so the response can be consumed by JavaScript

## Frontend: Client-Side DOCX Rendering

### Installation

```bash
npm install docx-preview
```

### Basic Implementation

```tsx
import React, { useEffect, useState, useRef } from 'react';
import { renderAsync } from 'docx-preview';

interface ResumePreviewProps {
  bullets: Array<{ original: string; enhanced: string }>;
  userId: string;
  sessionId?: string;
}

export const ResumePreview: React.FC<ResumePreviewProps> = ({
  bullets,
  userId,
  sessionId
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPreview = async () => {
    if (!containerRef.current) return;

    setIsLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('bullets', JSON.stringify(bullets));
      formData.append('user_id', userId);
      if (sessionId) {
        formData.append('session_id', sessionId);
      }

      const response = await fetch('https://your-backend.onrender.com/v2/preview', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Preview failed: ${response.statusText}`);
      }

      // Get DOCX blob
      const docxBlob = await response.blob();

      // Clear container and render DOCX
      containerRef.current.innerHTML = '';

      await renderAsync(docxBlob, containerRef.current, undefined, {
        className: 'docx-preview-container',
        inWrapper: true,
        ignoreWidth: false,
        ignoreHeight: false,
        ignoreFonts: false,
        breakPages: true,
        ignoreLastRenderedPageBreak: false,
        experimental: false,
        trimXmlDeclaration: true,
        useBase64URL: false,
        renderChanges: false,
        renderHeaders: true,
        renderFooters: true,
        renderFootnotes: true,
        renderEndnotes: true,
      });

    } catch (err) {
      console.error('Preview error:', err);
      setError(err instanceof Error ? err.message : 'Failed to load preview');
    } finally {
      setIsLoading(false);
    }
  };

  // Auto-update preview when bullets change (debounced)
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      loadPreview();
    }, 1000);

    return () => clearTimeout(timeoutId);
  }, [bullets]);

  return (
    <div className="resume-preview-wrapper">
      <div className="preview-header">
        <h3>Resume Preview</h3>
        <button onClick={loadPreview} disabled={isLoading}>
          {isLoading ? 'Loading...' : 'Refresh Preview'}
        </button>
      </div>

      {error && (
        <div className="preview-error">
          Error: {error}
        </div>
      )}

      {isLoading && (
        <div className="preview-loading">
          <div className="spinner" />
          <p>Generating preview...</p>
        </div>
      )}

      <div
        ref={containerRef}
        className="preview-container"
      />
    </div>
  );
};
```

### CSS Fixes for Common Issues

The `docx-preview` library has some rendering quirks. Here are the CSS fixes:

```css
/* Wrapper styling */
.resume-preview-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  background: #f5f5f5;
  overflow: hidden;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: white;
  border-bottom: 1px solid #e0e0e0;
  flex-shrink: 0;
}

.preview-container {
  flex: 1;
  overflow-y: auto;
  background: white;
  padding: 20px;
}

/* CRITICAL FIX: Replace square bullets with proper circles */
.docx-preview-container .docx-wrapper li::marker {
  content: '• ';
  font-size: 1em;
}

/* Alternative bullet fix if above doesn't work */
.docx-preview-container .docx-wrapper ul {
  list-style-type: disc !important;
}

.docx-preview-container .docx-wrapper ul li {
  list-style-type: disc !important;
}

/* Fix for bullet indentation */
.docx-preview-container .docx-wrapper ul {
  padding-left: 20px;
}

/* Preserve right-aligned text (e.g., dates) */
.docx-preview-container .docx-wrapper [style*="text-align:right"],
.docx-preview-container .docx-wrapper [style*="text-align: right"] {
  text-align: right !important;
}

/* Preserve center-aligned text */
.docx-preview-container .docx-wrapper [style*="text-align:center"],
.docx-preview-container .docx-wrapper [style*="text-align: center"] {
  text-align: center !important;
}

/* Fix font rendering to match DOCX */
.docx-preview-container .docx-wrapper {
  font-family: 'Calibri', 'Arial', 'Helvetica', sans-serif;
  font-size: 11pt;
  line-height: 1.15;
  color: #000;
}

/* Fix spacing between paragraphs */
.docx-preview-container .docx-wrapper p {
  margin: 0 0 6pt 0;
}

/* Fix bold text rendering */
.docx-preview-container .docx-wrapper strong,
.docx-preview-container .docx-wrapper b {
  font-weight: 700;
}

/* Fix link styling */
.docx-preview-container .docx-wrapper a {
  color: #0563C1;
  text-decoration: underline;
}

/* Page break visualization */
.docx-preview-container .docx-wrapper section {
  page-break-after: always;
  margin-bottom: 20px;
  border-bottom: 2px dashed #ccc;
  padding-bottom: 20px;
}

.docx-preview-container .docx-wrapper section:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

/* Error and loading states */
.preview-error {
  padding: 16px;
  background: #fee;
  color: #c00;
  text-align: center;
  margin: 16px;
  border-radius: 4px;
}

.preview-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #3498db;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
```

### Alternative Bullet Fix (If CSS Doesn't Work)

If CSS fixes don't resolve the square bullet issue, you can use the `className` option and target the list elements more aggressively:

```tsx
// In renderAsync options:
{
  className: 'docx-preview-container custom-bullets',
  // ... other options
}
```

```css
/* Force bullet type replacement */
.custom-bullets ul li::before {
  content: '• ';
  margin-right: 8px;
  font-weight: bold;
}

.custom-bullets ul li {
  list-style: none;
  position: relative;
  padding-left: 20px;
}
```

## Common Issues and Solutions

### Issue 1: Bullets Show as Squares

**Cause:** The `docx-preview` library sometimes renders bullet characters incorrectly.

**Solution:** Apply the CSS bullet fixes above. If that doesn't work, try:

1. Check that the DOCX bullets are using standard Word bullet formatting (not custom symbols)
2. Verify the `renderAsync` options include `ignoreWidth: false` and `ignoreFonts: false`
3. Use the alternative bullet fix with `::before` pseudo-element

### Issue 2: Right-Aligned Text Not Aligned

**Cause:** The library may not preserve all inline styles.

**Solution:** Use CSS to force alignment:

```css
.docx-preview-container [style*="text-align:right"] {
  text-align: right !important;
}
```

### Issue 3: Font Looks Different

**Cause:** Browser font substitution or library font rendering.

**Solution:**
- Ensure Calibri font is available (system font on Windows/Mac)
- Add font fallbacks in CSS
- Accept minor font variations (still pixel-perfect in downloaded DOCX)

### Issue 4: Spacing/Layout Issues

**Cause:** The library approximates DOCX spacing in HTML.

**Solution:**
- Adjust CSS margins and padding to match DOCX
- Use `breakPages: true` in renderAsync options
- Test with actual resume content to tune spacing

## Auto-Update on Bullet Changes

```tsx
// Debounced auto-update
useEffect(() => {
  const timeoutId = setTimeout(() => {
    loadPreview();
  }, 1000); // 1 second debounce

  return () => clearTimeout(timeoutId);
}, [bullets]); // Re-run when bullets change
```

## Disclaimer for Users

Since client-side rendering is an approximation, add this notice:

```tsx
<div className="preview-notice">
  ℹ️ Preview is optimized for accuracy but may show minor rendering differences.
  Downloaded DOCX will be pixel-perfect.
</div>
```

## Testing Checklist

1. ✅ Preview loads and displays resume content
2. ✅ Bullets appear as circles/dots (not squares)
3. ✅ Right-aligned text (dates, locations) renders correctly
4. ✅ Fonts match the downloaded DOCX (Calibri/Arial)
5. ✅ Spacing and margins look correct
6. ✅ Links are underlined and blue
7. ✅ Bold text renders properly
8. ✅ Page breaks are visible (if multi-page)
9. ✅ Preview updates when bullets are edited
10. ✅ Error handling works (network failure, invalid data)

## Performance Considerations

- DOCX rendering takes ~500-1000ms depending on document size
- Use debouncing (1 second) for auto-updates to avoid excessive API calls
- Show loading spinner during rendering
- Consider caching the preview DOCX blob if bullets haven't changed

## Alternative Libraries (If Needed)

If `docx-preview` continues to have rendering issues, consider:

1. **@microsoft/office-js** - Official Microsoft Office JavaScript API (requires Office Online integration)
2. **docx-preview-react** - React wrapper with better TypeScript support
3. **mammoth.js** (client-side) - Converts DOCX to HTML (loses pixel-perfect accuracy)
4. **Google Docs Viewer** (iframe embed) - Cloud-based viewer (requires public URL)

**Recommendation:** Stick with `docx-preview` and use CSS fixes. It's the only library that maintains pixel-perfect DOCX rendering accuracy needed for resume page break detection.
