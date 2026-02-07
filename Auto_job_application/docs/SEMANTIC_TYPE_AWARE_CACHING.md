# Semantic + Type-Aware Caching System

**Date**: 2026-02-05
**Status**: Implemented

## Philosophy: Robustness First, Optimization Later

> "Firstly it should be able to answer all questions without a failure. Then we think of where we can save money."

This system prioritizes **100% answer rate** over cost optimization. AI is the fallback for everything.

## Problem with Old System

### Dumb String Matching
```python
# OLD: Exact string match only
"Expected salary?" ≠ "Desired CTC?" ≠ "Compensation expectations?"
# Each stored separately, no learning
```

### No Type Awareness
```python
# OLD: Same answer for all field types
"Expected salary?" → "90 LPA" (cached)
# Works for text input ✅
# Fails for number input ❌ (expects "90")
```

### Cache Blocks AI
```python
# OLD: Cache hit returns immediately
if cached:
    return cached  # Even if "N/A" or wrong type!
# AI never gets a chance to fix mistakes
```

## New System Design

### 1. Type-Aware Caching

**Cache Key**: `question_hash + field_type`

```python
# NEW: Different answers for different field types
"Expected salary?" + type="number" → "90"  (cached separately)
"Expected salary?" + type="text"   → "90 LPA"  (cached separately)
```

**Database Schema:**
```sql
CREATE TABLE question_responses (
    id INTEGER PRIMARY KEY,
    question_hash TEXT,          -- Normalized question
    question_text TEXT,          -- Original question
    question_type TEXT,          -- salary, experience_years, etc.
    field_type TEXT,             -- number, text, email, url, etc.
    response TEXT,               -- The answer
    reuse_count INTEGER,         -- How many times reused
    created_at TIMESTAMP,
    last_used_at TIMESTAMP
);

CREATE INDEX idx_question_field_type ON question_responses(question_hash, field_type);
CREATE INDEX idx_question_type ON question_responses(question_type);
```

### 2. Semantic Aliasing via AI

**AI sees similar Q&A as context:**

```python
# When answering "Compensation expectations?", AI sees:
Previously Answered Similar Questions:
1. Q: Expected salary? (field type: text)
   A: 90 LPA
2. Q: Desired CTC? (field type: number)
   A: 90
3. Q: What is your expected compensation? (field type: text)
   A: 90 LPA

# AI learns: These are all asking the same thing!
# AI adapts answer to field type automatically
```

**Benefits:**
- AI recognizes semantic similarity
- Learns patterns from previous answers
- Builds knowledge base over time
- No manual alias mapping needed

### 3. AI-First Strategy

**New Decision Flow:**

```
Question + Field Type
    ↓
Exact Cache Hit? (question_hash + field_type)
    ↓ YES (and != "N/A")
    Return Cached Answer ✅
    ↓ NO
Rule-Based Answer?
    ↓ NO
Get Similar Q&A from DB (semantic context)
    ↓
Call AI with:
    - User profile
    - Job context
    - Similar Q&A examples
    - Field type guidance
    ↓
AI Returns Answer ✅
    ↓
Cache Answer (if not "N/A")
```

**Key Principle:** Cache only successful answers. Never cache "N/A" failures.

### 4. Field Type Guidance for AI

**AI receives explicit field type instructions:**

```python
if field_type == "number":
    "IMPORTANT: This is a NUMBER input. Return ONLY numeric value (e.g., '90' not '90 LPA')"

if field_type == "email":
    "IMPORTANT: This is an EMAIL input. Return only valid email address."

if field_type == "url":
    "IMPORTANT: This is a URL input. Return only valid URL."
```

## Implementation Details

### Detecting Field Type

```python
# In easy_apply_bot.py
input_type = await input_elem.get_attribute('type') or 'text'

# Pass to question handler
answer = question_handler.answer_question(
    question=label,
    field_type=input_type,  # ← NEW
    context=job_context
)
```

### Type-Aware Cache Lookup

```python
def _get_cached_response(question: str, field_type: str = None):
    question_hash = _hash_question(question)

    # Exact match: question + field type
    cursor.execute("""
        SELECT response FROM question_responses
        WHERE question_hash = ? AND field_type = ?
        ORDER BY reuse_count DESC
        LIMIT 1
    """, (question_hash, field_type))

    # Only return if NOT "N/A"
    if row and row[0] != "N/A":
        return row[0]

    return None  # Cache miss → Call AI
```

### Semantic Context Retrieval

```python
def _get_similar_qa(question: str, question_type: str, limit: int = 5):
    """Get similar Q&A from DB to help AI learn patterns."""

    cursor.execute("""
        SELECT question_text, response, field_type, reuse_count
        FROM question_responses
        WHERE question_type = ? AND response != 'N/A'
        ORDER BY reuse_count DESC
        LIMIT ?
    """, (question_type, limit))

    # Returns top 5 most-used Q&A of same type
```

## Examples

### Example 1: Salary Question Evolution

**First Application:**
```
Question: "Expected salary?" (type=text)
Cache: Miss
Similar Q&A: None
AI generates: "90 LPA"
Cached: question_hash="expected salary" + field_type="text" → "90 LPA"
```

**Second Application (Same Form):**
```
Question: "Expected salary?" (type=text)
Cache: HIT! → Returns "90 LPA" (no AI call)
```

**Third Application (Different Form, Number Input):**
```
Question: "Expected salary?" (type=number)
Cache: Miss (different field_type!)
Similar Q&A:
  1. "Expected salary?" (text) → "90 LPA"
AI sees context, understands field type=number
AI generates: "90"
Cached: question_hash="expected salary" + field_type="number" → "90"
```

**Fourth Application (Semantic Variant):**
```
Question: "Desired CTC?" (type=number)
Cache: Miss (different question)
Similar Q&A:
  1. "Expected salary?" (number) → "90"
  2. "Expected salary?" (text) → "90 LPA"
AI learns pattern, generates: "90"
Cached: question_hash="desired ctc" + field_type="number" → "90"
```

**Result:** Over time, database learns all variants of salary questions!

### Example 2: LinkedIn Profile URL

**First Time:**
```
Question: "LinkedIn Profile..." (type=text)
Cache: Miss
Rule-based: No match
Fallback: Returns "https://linkedin.com/in/somnath-ghosh"
Cached: question_hash="linkedin profile" + field_type="text" → URL
```

**Second Time (Variant):**
```
Question: "LinkedIn URL" (type=url)
Cache: Miss (different field_type)
Similar Q&A:
  1. "LinkedIn Profile..." (text) → "https://linkedin.com/in/somnath-ghosh"
AI adapts: Returns same URL (field_type=url guidance)
Cached: question_hash="linkedin url" + field_type="url" → URL
```

## Future-Proofing for Local LLM

This system prepares for cheap local/hosted LLM:

### Training Data Generation
```python
# Export Q&A database as training data
SELECT question_text, field_type, response, reuse_count
FROM question_responses
WHERE response != 'N/A'
ORDER BY reuse_count DESC;

# High reuse_count = high-quality training examples
```

### Fine-Tuning Dataset Format
```jsonl
{"prompt": "Expected salary? [field_type: number]", "completion": "90"}
{"prompt": "Expected salary? [field_type: text]", "completion": "90 LPA"}
{"prompt": "LinkedIn Profile... [field_type: text]", "completion": "https://linkedin.com/in/somnath-ghosh"}
```

### Local SLM Integration (Future)
```python
class QuestionHandler:
    def __init__(self, ai_provider='openclaw'):
        # ai_provider options:
        # - 'openclaw' (current - premium API)
        # - 'local-llm' (future - local Llama/Mistral)
        # - 'cheap-hosted' (future - cheap cloud LLM)
        self.ai_provider = ai_provider
```

## Migration from Old System

The system is **backwards compatible**:

1. **Adds `field_type` column** - existing rows have `NULL` field_type
2. **Updates indices** - composite index on (question_hash, field_type)
3. **Old cache still works** - `NULL` field_type matches legacy records
4. **Gradual migration** - new answers use field_type, old ones don't

No data loss, no manual migration needed!

## Cost Optimization Strategy (Future)

Once system is robust:

1. **Cache Hit Rate Analysis**
   ```sql
   SELECT question_type, AVG(reuse_count) as avg_reuse
   FROM question_responses
   GROUP BY question_type
   ORDER BY avg_reuse DESC;
   ```

2. **Identify High-Cost Questions**
   ```sql
   SELECT question_text, COUNT(*) as variants
   FROM question_responses
   WHERE question_type = 'salary'
   GROUP BY question_hash
   HAVING variants > 3;
   ```

3. **Add Pre-Computed Aliases** (optional, after robust)
   ```python
   ALIASES = {
       "expected salary": ["desired ctc", "compensation expectations", "salary expectation"],
       "linkedin profile": ["linkedin url", "linkedin link", "linkedin page"]
   }
   ```

But for now: **AI handles everything**. Robustness first!

## Testing the New System

### Test Case 1: Same Question, Different Types
```python
# Number input
answer1 = handler.answer_question("Expected CTC?", field_type="number")
assert answer1 == "90"  # No units

# Text input
answer2 = handler.answer_question("Expected CTC?", field_type="text")
assert answer2 == "90 LPA"  # With units
```

### Test Case 2: Semantic Variants
```python
# All should return similar answers
variants = [
    "Expected salary?",
    "Desired CTC?",
    "Compensation expectations?",
    "What is your expected pay?"
]

for question in variants:
    answer = handler.answer_question(question, field_type="text")
    assert "90" in answer  # All contain the salary value
```

### Test Case 3: No N/A Caching
```python
# First attempt fails
with mock.patch('AI.call', side_effect=Exception):
    answer = handler.answer_question("Unknown question?")
    assert answer == "N/A"

# Check it's NOT cached
cached = handler._get_cached_response("Unknown question?")
assert cached is None  # Not in cache!

# Second attempt can try again (AI fixed, or fallback added)
```

## Summary

**New System Principles:**
1. ✅ **Type-Aware** - Same question, different field types = different cache entries
2. ✅ **Semantic** - AI sees similar Q&A to learn patterns
3. ✅ **AI-First** - No cache hit? AI decides with full context
4. ✅ **No Failure Caching** - Never cache "N/A"
5. ✅ **Future-Proof** - Database becomes training data for local LLM

**Result:** 100% answer rate, continuous learning, future-ready for cost optimization.
