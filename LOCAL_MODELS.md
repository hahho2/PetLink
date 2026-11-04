# Local model connections

PetLink depends on the `LocalModelProvider` interface, not on a specific model
runtime. The initial provider uses the common OpenAI-compatible HTTP API.

Configure `ModelConfig.base_url` to the local server address and `model` to the
model name. The same provider can connect to runtimes such as:

- Ollama with its compatible API enabled
- LM Studio's local server
- llama.cpp server
- vLLM or another local OpenAI-compatible server

The task and conversation layers should receive a `LocalModelProvider` through
dependency injection. They must not import a runtime-specific client. Future
native adapters can implement the same interface when a runtime does not expose
the compatible API.

## Hosted APIs

The same interface supports hosted providers:

- OpenAI: use `OpenAICompatibleProvider` with an OpenAI base URL and API key.
- Grok: use `OpenAICompatibleProvider` with xAI's OpenAI-compatible base URL and API key.
- Google Gemini: use `GoogleGeminiProvider` with a Google API key.

Use `create_provider("openai", config)`, `create_provider("grok", config)`, or
`create_provider("google", config)` from application settings. Keys must be
provided at runtime, stored in Windows Credential Manager, excluded from logs,
and never committed to the repository. Cloud providers must be clearly marked
as sending conversation data off-device.
