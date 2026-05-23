# Providers

Agentheim Code is BYOK. You bring the local model or API key.

## Fastest Path

### Local Ollama

Onboarding and Settings check:

- `http://localhost:11434/api/tags`
- exposed app endpoint: `http://localhost:11434/v1`

If Ollama is running, Agentheim Code can surface detected model names during
onboarding.

### API Provider

Open the provider wizard and fill:

- profile name
- provider ID
- model ID
- required auth/endpoint fields

Test the connection before saving.

## Built-In Templates

- OpenAI
- Anthropic
- Google Gemini
- AWS Bedrock
- Azure Foundry
- Cohere
- Groq
- DeepSeek
- Mistral
- Ollama
- LM Studio
- Llama.cpp
- OCI GenAI
- Custom OpenAI-compatible endpoint

## Custom Endpoint

Use the custom endpoint template for:

- self-hosted OpenAI-compatible APIs
- internal gateways
- proxy endpoints

Required fields usually include:

- `endpoint`
- `api_key` when auth is enabled
- `model_id`

## Verification

CLI test:

```powershell
agentheim-code provider-test openai_v1 --api-key "sk-..." --endpoint "https://api.openai.com/v1" --model "gpt-4o-mini"
```

UI test:

- open Provider Wizard
- fill fields
- click `Test Connection`

Successful tests may still include a usage warning. That means inference works
but token/cost metadata is incomplete.

## Profiles And Models

- profile selector chooses saved config bundle
- model selector chooses planner model inside that profile
- keep `Auto` if you want the runtime defaults

## Secrets

- do not commit API keys
- prefer secret stores or environment variables
- provider summaries never return raw secrets through the UI APIs
