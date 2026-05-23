# Providers

Agentheim Code is BYOK. You bring the local model server or API credentials.

## Current Provider Model

The product stores provider setup in a compatibility profile store rooted under
the shared Agentheim config directory, not in the UI config TOML. These are
separate storage systems; see
`docs/adr/0001-config-surface-and-storage.md` for the boundary.

A profile contains:

- one or more provider accounts
- one or more model bindings
- a default profile name at the document level

The frontend currently focuses on a planner model for the active session.

## Fastest Path

### Local Ollama

Current onboarding auto-detection checks:

- `http://localhost:11434/api/tags`

If available, the app exposes it as:

- `http://localhost:11434/v1`

Only Ollama is auto-detected today.

### Add A Provider Manually

Open the provider wizard and fill in:

- profile name
- provider id
- model id
- provider-specific auth and endpoint fields

Test the connection before saving.

## Template Registry

The current shared template registry includes:

### Beta / non-experimental templates

- `openai_v1` — OpenAI
- `openai_compatible` — generic OpenAI-compatible API
- `azure_foundry` — Azure OpenAI / Foundry
- `gemini` — Google Gemini API
- `vertex_ai` — Google Vertex AI
- `ollama` — Ollama Local
- `lm_studio` — LM Studio
- `vllm` — vLLM
- `tgi` — HuggingFace TGI
- `llama_cpp` — llama.cpp Server

### Experimental templates

- `aws_bedrock`
- `oci_genai`
- `xai_grok`
- `anthropic`
- `kimi_moonshot`
- `mistral`
- `groq`
- `deepseek`
- `openrouter`
- `together`
- `cohere`
- `perplexity`
- `ollama_cloud`

The API currently exposes templates from the shared registry with
`include_experimental=true`.

`oci_genai` now uses a first-party Agentheim Code adapter rather than the older
vendored bridge.

## Custom And Self-Hosted Endpoints

The `openai_compatible` template is the current general-purpose option for:

- self-hosted OpenAI-style APIs
- internal gateways
- proxy endpoints
- local servers other than Ollama that speak an OpenAI-compatible interface

Typical required fields:

- `endpoint`
- `api_key` when auth is enabled
- `model_id`

## Verification

### CLI

```powershell
agentheim-code provider-test openai_v1 --api-key "sk-..." --endpoint "https://api.openai.com/v1" --model "gpt-4o-mini"
```

### UI

1. Open the provider wizard
2. Fill the template fields
3. Select `Test Connection`
4. Save only after a successful result

A successful test can still return a usage warning. That means inference worked
but the provider did not return token or cost metadata in a way the product can
use.

## Profiles, Models, And Health

- the profile selector chooses the saved profile bundle
- the model selector chooses the planner model within that profile
- `Auto` keeps runtime defaults
- `/api/coder/models` enriches model entries with persisted provider health when available

## Secrets

- do not commit API keys or exported profile documents with secrets
- UI profile summaries intentionally omit raw secrets
- provider credentials are stored through the shared secret store abstraction when possible
