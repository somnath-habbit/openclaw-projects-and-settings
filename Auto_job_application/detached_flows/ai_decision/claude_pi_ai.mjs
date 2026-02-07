#!/usr/bin/env node
/**
 * Lightweight Claude API wrapper using pi-ai library (same as OpenClaw).
 *
 * This uses the OAuth token from auth-profiles.json with the pi-ai library
 * which has the special integration to make Claude Code tokens work.
 *
 * Much faster than `openclaw agent` subprocess since it's a direct inference call.
 */
import { readFileSync } from 'fs';
import { homedir } from 'os';
import { join } from 'path';

// Import pi-ai from OpenClaw's node_modules
const piAiPath = join(homedir(), '.npm-global/lib/node_modules/openclaw/node_modules/@mariozechner/pi-ai/dist/index.js');
const { getModel, complete, getOAuthApiKey } = await import(piAiPath);

/**
 * Call Claude API using OAuth token via pi-ai library
 */
async function callClaude(prompt, maxTokens = 1024) {
    try {
        // Load OAuth credentials from auth-profiles.json
        const authPath = join(homedir(), '.openclaw/agents/main/agent/auth-profiles.json');
        const authData = JSON.parse(readFileSync(authPath, 'utf8'));

        // Get the OAuth token from profile
        const profileId = 'anthropic:claude-code-open-claw-token';
        const profile = authData.profiles[profileId];

        if (!profile || !profile.token) {
            throw new Error(`No OAuth token found in profile: ${profileId}`);
        }

        // Use token directly as API key (matches OpenClaw's auth-profiles/oauth.js:128-140)
        const apiKey = profile.token.trim();

        // Get Claude model
        const model = getModel('anthropic', 'claude-sonnet-4-5-20250929');

        // Build context
        const context = {
            messages: [
                { role: 'user', content: prompt }
            ]
        };

        // Call API with the OAuth token as API key
        const result = await complete(model, context, { apiKey });

        // Extract text from response
        const textContent = result.content.find(c => c.type === 'text');
        return textContent ? textContent.text : '';

    } catch (error) {
        console.error('Claude API error:', error.message);
        throw error;
    }
}

// CLI interface - accept prompt from command line
if (import.meta.url === `file://${process.argv[1]}`) {
    const args = process.argv.slice(2);

    if (args.length === 0) {
        console.error('Usage: claude_pi_ai.mjs "your prompt here"');
        process.exit(1);
    }

    const prompt = args.join(' ');

    try {
        const response = await callClaude(prompt);
        console.log(response);
    } catch (error) {
        console.error('Error:', error.message);
        process.exit(1);
    }
}

export { callClaude };
