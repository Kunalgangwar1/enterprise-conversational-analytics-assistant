# Multi-provider AI boundary

Application workflows depend on the provider-neutral `LLMClient`. The contract preserves system,
user, and assistant roles and supports plain text plus native, Pydantic-validated structured output.
Agents never import Gemini, Azure OpenAI, or a provider SDK directly.

## Providers and configuration

Gemini is the active development default:

```text
LLM_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_LLM_MODEL=gemini-3.8-flash
```

The adapter uses the official `google-genai` SDK. System instructions are sent through Gemini's
system-instruction field; user and assistant messages retain separate Gemini content roles.
Structured calls use Gemini's native response schema and return the requested Pydantic model—there
is no arbitrary prose JSON parsing. Traditional sampling values are not forwarded by default, so
existing provider-neutral requests remain compatible with Gemini models that ignore or deprecate
those controls.

Azure OpenAI remains a supported optional provider:

```text
LLM_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=replace_me
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
```

Changing `LLM_PROVIDER` is sufficient; no source commenting or agent changes are required. Unknown
providers fail clearly. Amazon Bedrock is a future adapter extension point and is not implemented.

## Lifecycle, errors, and testing

Both SDK clients are created lazily when the configured provider is first requested. FastAPI
startup therefore requires neither Gemini nor Azure credentials. SDK-native timeout and retry
configuration is used without an additional generic application retry loop.

Responses normalize text, provider, model, available request and usage metadata, and elapsed time
into `LLMResponse`. Authentication, throttling, timeout, provider, and structured-output failures
become the existing safe provider-neutral exceptions. Keys, prompts, raw responses, and headers are
not logged or included in exception messages.

Normal tests use mocked SDK boundaries or `FakeLLMClient` and make no provider calls. With a local
key intentionally configured, `python -m app.llm.smoke` sends one harmless prompt and prints only
safe response metadata.
