# Providers

Agentheim Code includes standalone provider/profile support. It can read the
same profile format and secret references as Agentheim Full, but does not depend
on Agentheim Full being installed.

## Supported Providers

Built-in templates cover the major cloud and local providers:

- **OpenAI** (`openai_v1`) — GPT-4o, GPT-4o-mini, etc.
- **Anthropic** (`anthropic`) — Claude Sonnet, Opus, etc.
- **Google Gemini** (`gemini`) — Gemini 2.0 Flash, etc.
- **AWS Bedrock** (`aws_bedrock`) — Claude via Bedrock
- **Azure Foundry** (`azure_foundry`) — Azure AI deployments
- **Cohere** (`cohere`)
- **Groq** (`groq`)
- **DeepSeek** (`deepseek`)
- **Mistral** (`mistral`)
- **Ollama** (`ollama`) — Local open-source models
- **OCI GenAI** (`oci_genai`) — Oracle Cloud
- **LM Studio** (`lm_studio`) — Local OpenAI-compatible server
- **Llama.cpp** (`llama_cpp`) — Local OpenAI-compatible server

## Bring Your Own Key (BYOK) & Custom Endpoints

You can connect to any OpenAI-compatible API endpoint using the **Custom Endpoint**
wizard template. This is useful for:

- Self-hosted models (vLLM, TGI, etc.)
- Third-party API proxies
- Internal corporate endpoints

Required fields: `api_key` and `endpoint` (base URL).

## Provider Testing

Before saving a provider profile, you can test the connection with a live inference
call. The test sends a minimal prompt and verifies:

- Latency (ms)
- Model response
- Token usage metadata (if available)

### CLI

```powershell
agentheim-code provider-test openai_v1 --api-key "sk-..." --endpoint "https://api.openai.com/v1" --model "gpt-4o-mini"
```

### Web UI

In the Provider Wizard, click **Test Connection** after filling in the fields.
A yellow warning banner appears if the provider works but does not return token
usage metadata — cost tracking will be unavailable for that provider.

## Session-Local Overrides

```powershell
agentheim-code coder --workspace . --profile default --provider openai --model gpt-4.1
```

In the app, use the model pill near the composer.

Provider secrets should be stored through the configured secret store or
environment variables. They should not be committed, printed in CLI JSON, or
written into `.ai-team/runs`.
