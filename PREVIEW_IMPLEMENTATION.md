# Document Preview Implementation Guide

## Backend: Preview Endpoint

We'll create a new `/v2/preview` endpoint that returns DOCX bytes (same logic as `/download` but optimized for preview).

```python
@app.post("/v2/preview")
async def preview_resume(
    bullets: str = Form(...),
    user_id: str = Form(...),
    session_id: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """
    Generate DOCX preview with current bullets.

    Returns DOCX file for client-side rendering.
    Same logic as /download but without filename header (for preview, not download).
    """
    # EXACT SAME LOGIC as /download endpoint
    # 1. Parse bullets JSON
    # 2. Get resume (uploaded, session, or base)
    # 3. Load DOCX
    # 4. Replace bullets
    # 5. Return DOCX bytes

    # ... (copy /download logic) ...

    # Return DOCX with preview-specific media type
    return Response(
        content=docx_data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        }
    )
```

**Key difference from /download:**
- No `Content-Disposition: attachment` header (we don't want browser to download)
- Returns raw DOCX bytes for in-browser rendering

## Frontend: React Component

### 1. Install docx-preview

```bash
npm install docx-preview
```

### 2. Create Preview Component

```typescript
import React, { useEffect, useRef, useState } from 'react';
import { renderAsync } from 'docx-preview';

interface ResumePreviewProps {
  bullets: Array<{ original: string; enhanced: string; used_facts?: string[] }>;
  userId: string;
  sessionId?: string;
  autoUpdate?: boolean; // If true, preview updates as bullets change
}

export const ResumePreview: React.FC<ResumePreviewProps> = ({
  bullets,
  userId,
  sessionId,
  autoUpdate = false
}) => {
  const previewContainerRef = useRef<HTMLDivElement>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPreview = async () => {
    if (!previewContainerRef.current) return;

    setIsLoading(true);
    setError(null);

    try {
      // Prepare form data
      const formData = new FormData();
      formData.append('bullets', JSON.stringify(bullets));
      formData.append('user_id', userId);
      if (sessionId) {
        formData.append('session_id', sessionId);
      }

      // Fetch DOCX from backend
      const response = await fetch('http://your-backend-url/v2/preview', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Preview failed: ${response.statusText}`);
      }

      // Get DOCX blob
      const docxBlob = await response.blob();

      // Clear previous preview
      if (previewContainerRef.current) {
        previewContainerRef.current.innerHTML = '';
      }

      // Render DOCX in browser
      await renderAsync(docxBlob, previewContainerRef.current, undefined, {
        className: 'docx-preview-content',
        inWrapper: true,
        ignoreWidth: false,
        ignoreHeight: false,
        renderHeaders: true,
        renderFooters: true,
        useBase64URL: true,
      });

    } catch (err) {
      console.error('Preview error:', err);
      setError(err instanceof Error ? err.message : 'Failed to load preview');
    } finally {
      setIsLoading(false);
    }
  };

  // Auto-update on bullet changes (with debounce)
  useEffect(() => {
    if (!autoUpdate) return;

    const timeoutId = setTimeout(() => {
      loadPreview();
    }, 1000); // 1 second debounce

    return () => clearTimeout(timeoutId);
  }, [bullets, userId, sessionId, autoUpdate]);

  return (
    <div className="resume-preview-wrapper">
      {/* Header with manual refresh button */}
      <div className="preview-header">
        <h3>Resume Preview</h3>
        <button
          onClick={loadPreview}
          disabled={isLoading}
          className="refresh-preview-btn"
        >
          {isLoading ? 'Updating...' : 'Refresh Preview'}
        </button>
      </div>

      {/* Error display */}
      {error && (
        <div className="preview-error">
          <p>Error loading preview: {error}</p>
          <button onClick={loadPreview}>Retry</button>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="preview-loading">
          <div className="spinner" />
          <p>Generating preview...</p>
        </div>
      )}

      {/* Preview container */}
      <div
        ref={previewContainerRef}
        className="docx-preview-container"
      />
    </div>
  );
};
```

### 3. Add Styling

```css
/* Preview wrapper */
.resume-preview-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  background: #f5f5f5;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: white;
  border-bottom: 1px solid #e0e0e0;
}

.refresh-preview-btn {
  padding: 8px 16px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.refresh-preview-btn:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.preview-error {
  padding: 16px;
  background: #fee;
  color: #c00;
  text-align: center;
}

.preview-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

/* DOCX preview container */
.docx-preview-container {
  flex: 1;
  overflow: auto;
  padding: 20px;
  background: white;
}

/* Make preview look like paper */
.docx-preview-content {
  max-width: 8.5in;
  min-height: 11in;
  margin: 0 auto;
  background: white;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  padding: 1in;
}

/* Page break indicator */
.docx-preview-content .page-break {
  border-top: 2px dashed #ff0000;
  margin: 20px 0;
  position: relative;
}

.docx-preview-content .page-break::after {
  content: "⚠️ PAGE 2 STARTS HERE";
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  background: #fff;
  padding: 0 10px;
  color: #ff0000;
  font-size: 12px;
  font-weight: bold;
}
```

### 4. Usage Example

```typescript
function ResumeCustomizer() {
  const [bullets, setBullets] = useState([...]);
  const [userId] = useState('user-123');
  const [sessionId] = useState('session-456');

  return (
    <div className="customizer-layout">
      {/* Left side: Bullet editor */}
      <div className="bullet-editor">
        {bullets.map((bullet, index) => (
          <BulletEditor
            key={index}
            bullet={bullet}
            onChange={(updated) => {
              const newBullets = [...bullets];
              newBullets[index] = updated;
              setBullets(newBullets);
            }}
          />
        ))}
      </div>

      {/* Right side: Live preview */}
      <div className="preview-panel">
        <ResumePreview
          bullets={bullets}
          userId={userId}
          sessionId={sessionId}
          autoUpdate={false} // Set to true for real-time updates
        />
      </div>
    </div>
  );
}
```

## Benefits of This Approach

✅ **Pixel-perfect accuracy** - Renders actual DOCX file
✅ **Shows page breaks** - User can see if resume goes to 2 pages
✅ **Same as download** - What you see is what you get
✅ **Fast** - Client-side rendering, no server round-trip after initial load
✅ **Works offline** - Once DOCX is loaded, can re-render instantly

## Performance Optimization

For better UX, consider:

1. **Debounced updates**: Wait 1-2 seconds after user stops typing before refreshing preview
2. **Manual refresh button**: Let user control when to update (recommended)
3. **Cache DOCX**: Store last generated DOCX to avoid unnecessary backend calls
4. **Loading states**: Show spinner while generating/rendering

## Page Count Detection

To warn user about page overflow:

```typescript
const detectPageCount = () => {
  const container = previewContainerRef.current;
  if (!container) return 1;

  // docx-preview adds page break elements
  const pageBreaks = container.querySelectorAll('.docx-page-break');
  return pageBreaks.length + 1;
};

useEffect(() => {
  const pageCount = detectPageCount();
  if (pageCount > 1) {
    alert('⚠️ Warning: Resume is now 2 pages. Consider shortening bullets.');
  }
}, [bullets]);
```
