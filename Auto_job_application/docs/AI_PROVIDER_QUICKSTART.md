# AI Provider Quick Start Guide

Quick guide to using the alternative AI providers in Auto_job_application.

---

## TL;DR

```bash
# Option 1: Use HuggingFace (recommended for cost-effectiveness)
echo "AI_PROVIDER=huggingface" >> .env
echo "HUGGINGFACE_API_KEY=your_key_here" >> .env

# Option 2: Use Ollama (recommended for privacy/free)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull phi3:mini && ollama serve &
echo "AI_PROVIDER=ollama" >> .env

# Option 3: Keep using OpenClaw (default)
# No configuration needed
```

---

## HuggingFace Setup (5 minutes)

### 1. Get API Key
Visit: https://huggingface.co/settings/tokens
- Click "New token"
- Name: "AutoJobApp"
- Type: "Read"
- Copy the token (starts with `hf_`)

### 2. Configure
Add to `.env`:
```bash
AI_PROVIDER=huggingface
HUGGINGFACE_API_KEY=hf_xxxxxxxxxxxxx
```

### 3. Done!
The scraper will now use HuggingFace for AI decisions.

**Cost:** Free tier covers ~2000-5000 inferences/month. $2/month for higher limits.

---

## Ollama Setup (10 minutes)

### 1. Install Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Pull Model
```bash
# Recommended: phi3:mini (fast, runs on CPU)
ollama pull phi3:mini

# Alternative: qwen2.5:7b (better quality, needs more RAM)
# ollama pull qwen2.5:7b
```

### 3. Start Server
```bash
ollama serve
```

Leave this running in the background. To run as a service:
```bash
# Create systemd service (optional)
sudo systemctl enable ollama
sudo systemctl start ollama
```

### 4. Configure
Add to `.env`:
```bash
AI_PROVIDER=ollama
OLLAMA_MODEL=phi3:mini
```

### 5. Done!
The scraper will now use local Ollama for AI decisions.

**Cost:** $0 (runs on your machine)

---

## Testing Your Provider

```bash
cd /home/somnath/.openclaw/workspace/Auto_job_application
python3 detached_flows/ai_decision/test_providers.py
```

You should see:
- ✓ Provider initialized successfully
- ✓ Error handling working correctly
- ✓ JSON parsing tests passing

---

## Troubleshooting

### HuggingFace: "API error 401"
- Check your API key is correct
- Make sure it starts with `hf_`
- Verify the token has Read permissions

### HuggingFace: "Model is loading"
- This is normal on first request
- Wait 10-30 seconds and try again
- The model will stay loaded for ~5 minutes

### Ollama: "Connection refused"
- Make sure Ollama is running: `ollama serve`
- Check the port: `curl http://localhost:11434/api/tags`
- Verify OLLAMA_ENDPOINT in .env matches

### Ollama: "Model not found"
- Pull the model first: `ollama pull phi3:mini`
- List available models: `ollama list`
- Match OLLAMA_MODEL in .env to pulled model

---

## Model Recommendations

### HuggingFace Models

| Model | Quality | Speed | RAM | Use Case |
|-------|---------|-------|-----|----------|
| Qwen/Qwen2.5-72B-Instruct | Excellent | Medium | N/A | Best quality (default) |
| mistralai/Mixtral-8x7B-Instruct-v0.1 | Very Good | Fast | N/A | Faster responses |
| meta-llama/Llama-3.1-70B-Instruct | Excellent | Medium | N/A | Alternative to Qwen |

To change model:
```bash
HUGGINGFACE_MODEL=mistralai/Mixtral-8x7B-Instruct-v0.1
```

### Ollama Models

| Model | Quality | Speed | RAM Needed | Use Case |
|-------|---------|-------|------------|----------|
| phi3:mini | Very Good | Very Fast | 4GB | Best for CPU (default) |
| llama3.2:3b | Good | Very Fast | 4GB | Lightweight alternative |
| qwen2.5:7b | Excellent | Fast | 8GB | Best quality |
| mistral:7b | Very Good | Fast | 8GB | Classic choice |

To change model:
```bash
# Pull new model
ollama pull qwen2.5:7b

# Update .env
OLLAMA_MODEL=qwen2.5:7b
```

---

## When to Use Which Provider

**Use OpenClaw (default)** if:
- You have an OpenClaw subscription
- You want the easiest setup (zero config)
- Quality is paramount
- Cost is not a concern

**Use HuggingFace** if:
- You want excellent quality at low cost
- $2/month budget is acceptable
- You don't want to manage infrastructure
- You need cloud-based inference

**Use Ollama** if:
- You want zero ongoing cost
- Privacy is important (no external API calls)
- You have a computer that can run local models
- You want the fastest inference (local)

**Use Anthropic** if:
- You already have an Anthropic API key
- You want Claude-quality responses
- You're willing to pay per-request pricing

---

## Performance Comparison

Based on our testing:

| Provider | Speed | Quality | Cost/1000 requests | Setup Time |
|----------|-------|---------|-------------------|------------|
| OpenClaw | 2-4s | Excellent | $0* | 0 min |
| HuggingFace | 2-3s | Excellent | $0.10-0.40 | 5 min |
| Anthropic | 2-3s | Excellent | $3-15 | 5 min |
| Ollama | 0.5-1s | Very Good | $0 | 10 min |

*Included with OpenClaw subscription

---

## Next Steps

1. Choose your provider based on the guide above
2. Follow the setup instructions
3. Update your `.env` file
4. Run the test script to verify
5. Start scraping with your new provider!

For detailed implementation information, see: `docs/PROVIDER_IMPLEMENTATION_SUMMARY.md`

For cost analysis and model selection, see: `docs/AI_PROVIDER_ALTERNATIVES.md`
