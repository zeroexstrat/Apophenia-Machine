# Config recipes — pointing azoth at an LLM

Config lives in `<repo>/azoth.config.yaml`. Inspect or set values:

```bash
azoth config --show
azoth config --set llm.provider openai_compatible
azoth config --set llm.model chema-qwen:latest
```

Environment variables override the file for a single run: `LLM_PROVIDER`, `LLM_BASE_URL`,
`LLM_MODEL`, `LLM_API_KEY`, `LLM_THINK`, `LLM_TIMEOUT`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`.

## Ollama native (default)

Calls Ollama's `/api/chat` directly with `think: false` for clean JSON.

```yaml
llm:
  provider: "ollama_native"
  base_url: "http://localhost:11434"
  model: "nemotron-3-super:cloud"
  api_key: "ollama"
  temperature: 0.3
  max_tokens: 4096
  think: false
  timeout: 300
```

Verify: `curl -s http://localhost:11434/api/tags` lists your model. Cloud models
(`:cloud`) require you to be signed in to Ollama, or probe calls fail at request time —
which is exactly what `preflight.py` catches.

## OpenAI-compatible (LM Studio, vLLM, llama.cpp server, etc.)

```bash
azoth config --set llm.provider openai_compatible
azoth config --set llm.base_url http://localhost:1234/v1
azoth config --set llm.model your-model-id
azoth config --set llm.api_key sk-anything
```

## Exhaustion budget

```yaml
exhaustion:
  llm_max_tokens: 384   # per exhaustion batch; raise for richer runs, lower for slow cloud models
```

## Domains

Seeded: physics, ML, philosophy, neuroscience, mathematics, biology, unclassified.
You rarely edit this by hand — `azoth reclassify` (with an LLM) proposes and adopts new
domains automatically. To set the list explicitly, pass a JSON list:

```bash
azoth config --set domains '["physics", "ML", "biology", "chemistry", "unclassified"]'
```
