---
name: ai-integration
description: Use this skill whenever the user mentions AI integration, LLM usage, prompting, adding AI to a workflow, or configuring AI models. This covers all patterns, best practices, and node configurations for AI.
triggers: [AI integration, LLM, prompting, AI model, AI workflow, embedding, vector]
tier: specialized
dependencies: []
---

# AI Integration Patterns — Skill Reference

## LLM API Integration Standards

### Provider Priority
1. **Claude (Anthropic)** — Default for complex reasoning, long context, structured output
2. **GPT-4 (OpenAI)** — Fallback, function calling, vision tasks
3. **Gemini (Google)** — Large context windows, multimodal
4. **ElevenLabs** — Voice synthesis
5. **Perplexity** — Real-time web research

### Prompt Engineering Standards
- Always include a system prompt defining role and constraints
- Use structured output (JSON mode) when parsing is needed downstream
- Include examples (few-shot) for complex classification tasks
- Set explicit output format: "Respond ONLY with valid JSON. No preamble."
- Include guardrails: "If you cannot answer, respond with {\"error\": \"reason\"}"

### RAG (Retrieval Augmented Generation) Architecture
```
User Query → Embed Query → Vector Search (Pinecone) → Retrieve Top K chunks
    → Build Prompt (System + Context Chunks + Query) → LLM → Parse → Respond
```

Key decisions:
- Chunk size: 500-1000 tokens (overlap 100 tokens)
- Embedding model: text-embedding-3-small (OpenAI) or voyage-3 (Anthropic)
- Top K: 5-10 chunks depending on context window
- Always include source attribution in responses

### Multi-Agent Orchestration
```
Orchestrator Agent
  ├── Research Agent (web search, data gathering)
  ├── Analysis Agent (data processing, calculations)
  ├── Writing Agent (content generation, formatting)
  └── Execution Agent (API calls, database updates)
```

Rules:
- Each agent has a single, clear responsibility
- Orchestrator decides which agent to invoke based on the task
- Agents return structured results to the orchestrator
- Failures in one agent don't crash the pipeline

### Voice Agent Architecture (Twilio + ElevenLabs)
```
Inbound Call → Twilio Webhook → n8n Workflow → Transcribe (Whisper/Deepgram)
    → AI Process (Claude) → Text-to-Speech (ElevenLabs) → Respond via Twilio
```

### Error Handling for AI Calls
- Always set timeouts (30-60s for LLM calls)
- Implement retry with exponential backoff (3 attempts)
- Have a fallback response for when AI fails
- Log all AI interactions for debugging and improvement
- Monitor token usage and costs

### Cost Optimization
- Use Haiku/GPT-4-mini for simple classification tasks
- Use Sonnet/GPT-4 for complex reasoning
- Cache common responses where appropriate
- Batch operations when possible
- Set max_tokens appropriately (don't use 4096 for a yes/no answer)

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]]
