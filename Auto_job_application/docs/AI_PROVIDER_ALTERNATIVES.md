# AI Provider Alternatives — Cost-Optimized Options

> **Purpose:** Document lightweight, cost-effective AI providers for the decision engine
> **Status:** Planning — implementation tracked in separate task
> **Date:** 2026-02-04

---

## Current State

**Default:** OpenClaw agent (OAuth-based, uses Claude Sonnet/Haiku)
- Cost: Included with OpenClaw OAuth session
- Speed: ~2-4s per decision
- Quality: Excellent
- Limitation: Uses premium Claude models

**Problem:** For high-volume runs or budget constraints, we need cheaper alternatives.

---

## Use Case Analysis

The AI decision engine's job is simple:
1. **Input:** Accessibility tree (text), page goal, user context
2. **Task:** Decide next action (click, type, wait, skip)
3. **Output:** Structured JSON with action + confidence

**Key insight:** This is a narrow task that doesn't need a huge model. Even 7B-13B models can handle this well.

**Frequency:** AI only fires when structured extraction fails (rare for stable pages)
- Normal scraping: 0 AI calls
- Unexpected popup: 1 AI call per popup
- Estimate: <10 AI calls per 100 jobs scraped

---

## Option 1: Hugging Face Inference API (Recommended)

### Why This Fits
- $2/month credit covers ~2000-5000 inference calls (depending on model)
- Many free-tier models available
- Simple API (similar to Anthropic)
- No infrastructure management

### Recommended Models

| Model | Size | Speed | Cost | Best For |
|---|---|---|---|---|
| **Qwen/Qwen2.5-72B-Instruct** | 72B | Medium | Free tier | Best quality, good at structured output |
| **mistralai/Mixtral-8x7B-Instruct** | 8x7B MoE | Fast | Free tier | Fast inference, good reasoning |
| **meta-llama/Llama-3.1-70B-Instruct** | 70B | Medium | Paid | Excellent if free tier runs out |
| **google/gemma-2-27b-it** | 27B | Fast | Free tier | Lightweight, fast, good enough |

**Recommendation:** Start with **Qwen2.5-72B** (best quality) or **Mixtral-8x7B** (fastest).

### Implementation Plan

**File:** `detached_flows/ai_decision/providers/huggingface_provider.py`

```python
import requests
import json
from detached_flows.ai_decision.providers.base import BaseProvider

class HuggingFaceProvider(BaseProvider):
    def __init__(self, api_key: str, model: str = "Qwen/Qwen2.5-72B-Instruct"):
        self.api_key = api_key
        self.model = model
        self.endpoint = f"https://api-inference.huggingface.co/models/{model}"

    async def analyze(self, screenshot_b64, a11y_snapshot, context, goal):
        prompt = f"""Given this LinkedIn page state, decide the next action.

Goal: {goal}
User context: {json.dumps(context)}
Page accessibility tree:
{a11y_snapshot[:2000]}

Return JSON only:
{{"action": "click|type|wait|skip", "target": "...", "text": "...", "reason": "...", "confidence": 0.0-1.0}}"""

        response = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"inputs": prompt, "parameters": {"max_new_tokens": 200}},
            timeout=30
        )

        result = response.json()
        # Parse and return action dict
```

**Config updates:**
- Add `HUGGINGFACE_API_KEY` to `.env`
- Add `HUGGINGFACE_MODEL` (optional, defaults to Qwen2.5-72B)
- Update `decision_engine.py` to support `AI_PROVIDER=huggingface`

**Estimated cost:** $0.50-$2/month for typical usage (100-500 jobs/month)

---

## Option 2: Ollama (Self-Hosted, Free)

### Why This Fits
- 100% free (runs on your hardware)
- Fast local inference
- No API rate limits
- Privacy (no external calls)

### Recommended Models for CPU/GPU

| Model | Size | RAM | Speed | Quality |
|---|---|---|---|---|
| **Phi-3-mini** | 3.8B | 4GB | Very fast | Excellent reasoning for small model |
| **Llama 3.2 3B** | 3B | 4GB | Very fast | Meta's latest, good at instructions |
| **Qwen2.5:7b** | 7B | 8GB | Fast | Best quality in this size class |
| **Mistral 7B** | 7B | 8GB | Fast | Classic choice, proven quality |

**Recommendation:** **Phi-3-mini** (runs on CPU, perfect for this task)

### Implementation Plan

**Setup Ollama:**
```bash
# Install
curl -fsSL https://ollama.com/install.sh | sh

# Pull model
ollama pull phi3:mini

# Run server (starts on localhost:11434)
ollama serve
```

**File:** `detached_flows/ai_decision/providers/ollama_provider.py`

```python
import requests
import json
from detached_flows.ai_decision.providers.base import BaseProvider

class OllamaProvider(BaseProvider):
    def __init__(self, model: str = "phi3:mini", endpoint: str = "http://localhost:11434"):
        self.model = model
        self.endpoint = endpoint

    async def analyze(self, screenshot_b64, a11y_snapshot, context, goal):
        prompt = f"""Decide the next browser action for this LinkedIn automation task.

Goal: {goal}
Context: {json.dumps(context)}
Page state (accessibility tree):
{a11y_snapshot[:2000]}

Return ONLY valid JSON: {{"action": "click|type|wait|skip", "target": "...", "text": "...", "reason": "...", "confidence": 0.0-1.0}}"""

        response = requests.post(
            f"{self.endpoint}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=30
        )

        result = response.json()
        # Parse result["response"] and extract JSON
```

**Config updates:**
- Add `OLLAMA_MODEL` to `.env` (default: phi3:mini)
- Add `OLLAMA_ENDPOINT` (default: http://localhost:11434)
- Update `decision_engine.py` to support `AI_PROVIDER=ollama`

**Cost:** $0 (runs on your machine)
**Tradeoff:** Slightly lower quality than 70B models, but still very capable for this task

---

## Option 3: Fine-Tuned SLM (Future)

### Why This Would Be Ideal
- 10x faster inference
- 100x cheaper (tiny model, runs anywhere)
- Optimized for this specific task
- Could run on edge devices

### Training Data Collection
Before fine-tuning, collect examples:
1. Run scraper with current AI provider (OpenClaw/HuggingFace)
2. Log each AI decision to `data/ai_decisions.json`:
   ```json
   {
     "timestamp": "...",
     "a11y_snapshot": "...",
     "context": {...},
     "goal": "...",
     "decision": {...},
     "correct": true/false  // manual label or validation
   }
   ```
3. After 100-200 examples, fine-tune a small model

### Recommended Base Models for Fine-Tuning
- **TinyLlama 1.1B** (ultra-fast, runs on CPU)
- **Phi-2 2.7B** (excellent reasoning, small)
- **Qwen2.5 1.5B** (latest, efficient)

### Fine-Tuning Process
```bash
# Use Hugging Face AutoTrain or custom LoRA
autotrain llm --train --model TinyLlama/TinyLlama-1.1B-Chat-v1.0 \
  --data-path ./ai_decisions.jsonl \
  --text-column prompt \
  --lr 2e-4 --epochs 3
```

**Estimated cost:** $5-20 for fine-tuning on Hugging Face / Colab
**Result:** Model that runs in <100ms, perfect accuracy for this narrow task

---

## Implementation Priority

1. **Phase 1 (Immediate):** HuggingFace provider
   - Quickest to implement (~1 hour)
   - Proven quality
   - $2/month budget works
   - Fallback from OpenClaw

2. **Phase 2 (Next week):** Ollama provider
   - Zero ongoing cost
   - Good for development/testing
   - Privacy benefit
   - Run on local machine or cheap VPS

3. **Phase 3 (After data collection):** Fine-tuned SLM
   - Collect 100-200 decision examples
   - Fine-tune TinyLlama or Phi-2
   - Deploy as primary provider
   - OpenClaw/HuggingFace as fallback

---

## Cost Comparison (Monthly)

| Provider | Cost | Quality | Speed | Notes |
|---|---|---|---|---|
| OpenClaw (current) | $0* | Excellent | 2-4s | *Included with OAuth |
| Hugging Face Free | $0 | Excellent | 2-3s | Rate limited |
| Hugging Face Paid | $2-5 | Excellent | 1-2s | $2/month credit |
| Ollama (local) | $0 | Very good | 0.5-1s | Runs on your hardware |
| Fine-tuned SLM | $0 | Optimized | 0.1-0.3s | After initial training cost |

---

## Decision Matrix

**Choose Hugging Face if:**
- Want minimal setup
- $2/month budget is fine
- Need proven quality immediately
- Don't want to manage infrastructure

**Choose Ollama if:**
- Have spare compute (even modest)
- Want zero ongoing cost
- Privacy is important
- Willing to accept slightly lower quality

**Choose Fine-tuned SLM if:**
- Have collected training data (100+ examples)
- Want maximum speed/efficiency
- Long-term cost optimization matters
- This is a production deployment

---

## Implementation Task

Create providers for HuggingFace and Ollama as separate task/agent.

**Files to create:**
1. `detached_flows/ai_decision/providers/huggingface_provider.py`
2. `detached_flows/ai_decision/providers/ollama_provider.py`
3. Update `detached_flows/ai_decision/decision_engine.py` to support both
4. Update `detached_flows/config.py` with new env vars
5. Update `.env.example` with HuggingFace/Ollama settings
6. Test both providers with saved page snapshots

**Estimated time:** 2-3 hours for both providers + testing

---

**Recommendation for now:** Test with OpenClaw (already implemented), then spawn sub-agent to implement HuggingFace + Ollama providers as fallback options.
