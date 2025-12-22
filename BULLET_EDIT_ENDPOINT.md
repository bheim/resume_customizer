# Bullet Edit Endpoint

## Overview

The `/v2/bullets/edit` endpoint allows users to edit optimized bullets with real-time validation and automatic character limit enforcement.

## Endpoint Details

**URL:** `POST /v2/bullets/edit`
**Content-Type:** `application/json`

## Request Format

```json
{
  "bullet_text": "The edited bullet text",
  "original_bullet_text": "The original bullet text (optional)"
}
```

### Parameters

- `bullet_text` (required): The edited bullet text to validate
- `original_bullet_text` (optional): The original bullet text, used to determine the appropriate character limit. If not provided, defaults to a medium limit (200 chars).

## Response Format

```json
{
  "validated_text": "The processed bullet text (may be shortened if needed)",
  "char_count": 95,
  "char_limit": 100,
  "exceeds_limit": false,
  "was_shortened": false,
  "original_length": 95
}
```

### Response Fields

- `validated_text`: The validated/processed bullet text (automatically shortened if it exceeded the limit)
- `char_count`: Final character count of the validated text
- `char_limit`: Character limit based on the original bullet length
- `exceeds_limit`: Boolean indicating if the edited text exceeded the limit
- `was_shortened`: Boolean indicating if the text was automatically shortened by the LLM
- `original_length`: Length of the edited text before validation

## Character Limits

The endpoint uses tiered character limits based on the original bullet length:

- Original ≤ 110 chars → Limit: 100 chars
- Original 111-210 chars → Limit: 200 chars
- Original > 210 chars → Limit: 300 chars

If no original text is provided, defaults to 200 char limit.

## Automatic Shortening

If the edited bullet exceeds the character limit, the endpoint will:

1. Use an LLM to intelligently shorten the bullet while preserving:
   - Key numbers and metrics
   - Core results and achievements
   - Overall meaning
2. Make up to 3 attempts to get within the limit
3. Truncate if still too long after attempts

## Frontend Integration Example

```javascript
async function editBullet(editedText, originalText) {
  const response = await fetch('http://localhost:8000/v2/bullets/edit', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      bullet_text: editedText,
      original_bullet_text: originalText
    })
  });

  const result = await response.json();

  // Show warning if shortened
  if (result.was_shortened) {
    console.warn(`Bullet was automatically shortened from ${result.original_length} to ${result.char_count} chars`);
  }

  // Update UI with validated text
  return result.validated_text;
}
```

## Use Cases

1. **Real-time validation**: Call this endpoint as the user types to show character count and warnings
2. **Auto-correction**: When user clicks "Save" on an edited bullet, validate and apply the result
3. **Batch validation**: Validate all edited bullets before download

## Testing

Run the test suite:

```bash
python test_bullet_edit.py
```

The test suite includes:
- Bullet within character limit
- Bullet exceeding character limit (tests automatic shortening)
- Bullet without original text (tests default limit)

## Frontend Flow

1. User views optimized bullets
2. User clicks pen icon to edit a bullet
3. Frontend shows edit modal/input
4. **[NEW]** User edits bullet text
5. **[NEW]** Frontend calls `/v2/bullets/edit` to validate
6. **[NEW]** Frontend displays validated text and warnings if needed
7. User confirms and continues to download

## Error Handling

The endpoint returns standard HTTP error codes:

- `200 OK`: Validation successful
- `422 Unprocessable Entity`: Invalid request format
- `500 Internal Server Error`: Server-side processing error

Example error response:

```json
{
  "detail": "Error message describing what went wrong"
}
```
