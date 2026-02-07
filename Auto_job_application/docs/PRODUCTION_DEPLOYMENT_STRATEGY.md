# Production Deployment Strategy

## Current Status (2026-02-05)

**Local Development: ✅ Working**
- Fast Claude integration via pi-ai library
- Response time: 1-3 seconds
- Uses OAuth token from `claude setup-token`
- No additional API costs

**Production (EC2/Docker): ⚠️ OAuth Token Challenge**
- OAuth tokens require browser authentication
- Cannot be generated on headless servers
- Manual token refresh required

## Recommended Approach: Environment-Based Provider Selection

### Architecture

```python
if os.getenv('DEPLOYMENT_ENV') == 'production':
    # EC2/Docker: HuggingFace primary (no browser needed)
    AI_PROVIDER = 'huggingface'
    FALLBACK = 'patterns'
else:
    # Local: Fast Claude primary
    AI_PROVIDER = 'claude-fast'
    FALLBACK = 'huggingface'
```

### Provider Comparison

| Feature | Claude (OAuth) | HuggingFace Pro | Anthropic API Key |
|---------|---------------|-----------------|-------------------|
| Speed | 1-3s | 2-5s | 1-3s |
| Cost | $0 (included) | $0 (included) | $$ (extra cost) |
| Browser needed | ✅ Yes | ❌ No | ❌ No |
| Headless compatible | ❌ No | ✅ Yes | ✅ Yes |
| Token rotation | Manual | Programmatic | Programmatic |
| Best for | Local dev | Production | N/A |

## Implementation Plan

### Phase 1: HuggingFace Integration (NEXT)

**Files to update:**
1. `detached_flows/ai_decision/huggingface_api.py` - Complete implementation
2. `detached_flows/ai_decision/question_handler.py` - Add HF provider
3. `detached_flows/config.py` - Add environment detection

**Environment Variables:**
```bash
# Local development
DEPLOYMENT_ENV=local
# Uses Claude OAuth token automatically

# Production (EC2)
DEPLOYMENT_ENV=production
HUGGINGFACE_API_KEY=hf_xxxxxxxxxxxxx
# Fetches from HF Pro subscription
```

**Code Changes:**
```python
# question_handler.py

def _generate_ai_answer(self, prompt, ...):
    """Generate answer with environment-based provider selection."""

    if os.getenv('DEPLOYMENT_ENV') == 'production':
        # Production: HuggingFace primary
        try:
            from detached_flows.ai_decision.huggingface_api import call_huggingface_api
            return call_huggingface_api(prompt)
        except Exception as e:
            logger.warning(f"HuggingFace failed: {e}, falling back to rules")
            return self._generate_rule_based_answer(...)
    else:
        # Local: Fast Claude primary
        try:
            from detached_flows.ai_decision.claude_fast import call_claude_fast
            return call_claude_fast(prompt)
        except Exception as e:
            logger.warning(f"Claude failed: {e}, trying HuggingFace")
            try:
                from detached_flows.ai_decision.huggingface_api import call_huggingface_api
                return call_huggingface_api(prompt)
            except:
                return self._generate_rule_based_answer(...)
```

### Phase 2: Credential Management

**Option A: Environment Variables (Simple)**
```bash
# .env file (not committed)
HUGGINGFACE_API_KEY=hf_xxxxx
CLAUDE_OAUTH_TOKEN=sk-ant-oat01-xxxxx  # For local only
```

**Option B: Encrypted Credential Store (Secure)**
Use the creds manager we built:
1. Store HF API key via web UI
2. Broker retrieves from encrypted SQLite
3. Automatic key rotation support

### Phase 3: Docker Deployment

**Dockerfile:**
```dockerfile
FROM python:3.10-slim

# Install Node.js for pi-ai (local dev only)
RUN apt-get update && apt-get install -y nodejs npm

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY . /app
WORKDIR /app

# Set production environment
ENV DEPLOYMENT_ENV=production
ENV HUGGINGFACE_API_KEY=${HUGGINGFACE_API_KEY}

CMD ["python", "detached_flows/Playwright/apply_jobs_batch.py"]
```

**Deploy to EC2:**
```bash
# Build image
docker build -t auto-job-apply .

# Run with HF token
docker run -e HUGGINGFACE_API_KEY=hf_xxxxx auto-job-apply
```

## Testing Checklist

**Before Production Deployment:**
- [ ] HuggingFace API integration complete
- [ ] Environment-based provider selection working
- [ ] Test with DEPLOYMENT_ENV=production locally
- [ ] Verify HF model quality (Qwen vs Claude comparison)
- [ ] Test token rotation/refresh
- [ ] Docker image builds successfully
- [ ] EC2 instance configured with secrets
- [ ] Monitor cost and usage

## Alternative: Token Sync Service

For teams wanting to use Claude in production:

**Architecture:**
1. Local machine: Browser available, generates OAuth token
2. Token sync service: Securely uploads token to S3/Secrets Manager
3. EC2 instances: Download fresh token periodically
4. Monitor token expiry and alert for manual refresh

**Implementation:**
```bash
# Local: Generate and upload token
claude setup-token | scripts/sync_token.sh

# EC2: Download token (cron job every hour)
0 * * * * /app/scripts/fetch_token.sh
```

**Pros:**
- Use Claude (better quality)
- No extra API costs

**Cons:**
- Complex setup
- Still requires manual browser auth
- Token expiry monitoring needed

## Recommendation

**For Production: Use HuggingFace Pro**
- Simplest solution
- No browser dependency
- Already paid for
- Good quality (Qwen 2.5-72B)
- Programmatic token management

**For Local Development: Keep Fast Claude**
- Best quality
- Fastest (1-3s)
- No extra cost
- Easy to use

This hybrid approach gives us the best of both worlds.
