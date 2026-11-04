from petlink.models import ChatMessage, ModelConfig, OpenAICompatibleProvider


def test_payload_is_runtime_neutral():
    provider = OpenAICompatibleProvider(ModelConfig("http://127.0.0.1:11434", "qwen2.5"))
    payload = provider._payload([ChatMessage("user", "hello")], response_format={"type": "json_object"})

    assert payload["model"] == "qwen2.5"
    assert payload["messages"] == [{"role": "user", "content": "hello"}]
    assert payload["response_format"] == {"type": "json_object"}


def test_endpoint_is_openai_compatible():
    provider = OpenAICompatibleProvider(ModelConfig("http://localhost:1234/", "local-model"))

    request = provider._request_object("/chat/completions", {"model": "local-model"})

    assert request.full_url == "http://localhost:1234/v1/chat/completions"
    assert request.method == "POST"
