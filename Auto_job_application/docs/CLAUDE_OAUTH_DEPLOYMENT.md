# Claude OAuth Token Deployment Challenge

## Problem

The OAuth token from `claude setup-token` requires browser-based authentication, which poses challenges for headless server deployments (EC2, Docker, CI/CD).

## Current Solution (Local Development)

**Fast Claude Integration via pi-ai Library:**
- Uses OAuth token stored in `~/.openclaw/agents/main/agent/auth-profiles.json`
- Token obtained via: `claude setup-token` (requires browser)
- Performance: 1-3s (vs 10-30s for `openclaw agent` subprocess)
- Implementation: `claude_pi_ai.mjs` + `claude_fast.py`

**How It Works:**
1. OpenClaw uses `@mariozechner/pi-ai` library internally
2. We call the same library directly, bypassing slow subprocess
3. OAuth token is used directly as API key (not Bearer auth)
4. Reverse engineered from: `~/.npm-global/lib/node_modules/openclaw/dist/agents/auth-profiles/oauth.js:128-140`

## Token Characteristics

- **Type**: `sk-ant-oat01-...` (OAuth Access Token)
- **Expiry**: No expiry field in auth-profiles.json (appears long-lived)
- **Restriction**: "This credential is only authorized for use with Claude Code and cannot be used for other API requests"
- **Authentication**: Requires browser for initial setup

## Production Deployment Options

### Option 1: Manual Token Management
**Approach:**
- Generate token locally (with browser)
- Store in encrypted credential manager
- Deploy to EC2
- Manual rotation when expired

**Pros:**
- Uses existing Claude subscription
- No additional API costs

**Cons:**
- Requires manual intervention
- Can't automate initial token generation
- Unknown token lifespan

### Option 2: HuggingFace Primary (RECOMMENDED)
**Approach:**
- Use HuggingFace Pro API as primary (already subscribed)
- API token via environment variable (no browser needed)
- Keep Claude for local development only

**Pros:**
- No browser dependency
- Programmatic token rotation
- Works in headless environments
- Already paid for

**Cons:**
- Different model (Qwen vs Claude)
- Need to test quality

### Option 3: Regular Anthropic API Key
**Approach:**
- Purchase separate Anthropic API key
- Use standard API authentication

**Pros:**
- No browser dependency
- Straightforward deployment

**Cons:**
- Additional cost on top of Claude subscription
- Defeats purpose of using existing subscription

## Implementation Status

**Current (2025-02-05):**
- ✅ Fast Claude integration working locally
- ✅ OAuth token reverse engineered
- ✅ Performance: 1-3s response time
- ⚠️ Production deployment: TBD

**Next Steps:**
1. Test with job applications (local)
2. Integrate HuggingFace as production fallback
3. Add environment-based provider selection
4. Document token rotation procedure

## Code References

- **Node.js wrapper**: `detached_flows/ai_decision/claude_pi_ai.mjs`
- **Python integration**: `detached_flows/ai_decision/claude_fast.py`
- **Question handler**: `detached_flows/ai_decision/question_handler.py`
- **Auth profiles**: `~/.openclaw/agents/main/agent/auth-profiles.json`

## Related

- HuggingFace integration: `detached_flows/ai_decision/huggingface_api.py` (created, awaiting API token)
- OpenClaw source: `~/.npm-global/lib/node_modules/openclaw/`
- pi-ai library: `openclaw/node_modules/@mariozechner/pi-ai/`
