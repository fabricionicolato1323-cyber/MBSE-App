import json

from llm_service import ModelSelectionError, OllamaLLM


class FakeOllama(OllamaLLM):
    def __init__(self, installed: list[str], selected: str | None = None) -> None:
        self._installed = installed
        self.last_payload = None
        self.response_content = {"valid": True}
        super().__init__(
            base_url="http://ollama.invalid",
            model=selected,
            timeout_seconds=1,
        )

    def _request(self, path, payload=None):
        if path == "/api/tags":
            return {"models": [{"name": name} for name in self._installed]}
        if path == "/api/chat":
            self.last_payload = payload
            return {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(self.response_content),
                },
                "total_duration": 2_000_000_000,
                "load_duration": 250_000_000,
                "prompt_eval_count": 20,
                "eval_count": 4,
            }
        raise AssertionError(path)


def main() -> None:
    one_installed = ["test-model-from-runtime"]
    client = FakeOllama(one_installed)
    assert client.model == one_installed[0]

    schema = {
        "type": "object",
        "properties": {"valid": {"type": "boolean"}},
        "required": ["valid"],
        "additionalProperties": False,
    }
    start = client.metric_count()
    result = client._json_chat(
        [{"role": "user", "content": "Return JSON"}],
        schema,
    )
    assert result == {"valid": True}
    assert client.last_payload["model"] == one_installed[0]
    assert client.last_payload["format"] == schema
    assert client.metrics[-1].ollama_seconds == 2.0
    summary = client.timing_summary_since(start)
    assert "Ollama responses: 1" in summary
    assert "Ollama: 2.00 s" in summary

    client.response_content = {
        "coverage": "SUPPORTED",
        "answer": "A graph-grounded answer.",
        "claim_ids": ["CLAIM-TEST-001"],
    }
    knowledge_result = client.answer_from_knowledge(
        "What is an Operational Actor?",
        [
            {
                "claim_id": "CLAIM-TEST-001",
                "text": "Evidence text",
                "status": "ArcadiaReference",
                "source": ["Test source"],
                "locator": "section 1",
            }
        ],
    )
    assert knowledge_result["coverage"] == "SUPPORTED"
    assert client.last_payload["model"] == one_installed[0]
    assert client.last_payload["format"]["required"] == [
        "coverage",
        "answer",
        "claim_ids",
    ]

    configured = FakeOllama(
        ["test-model-a", "test-model-b"],
        selected="test-model-b",
    )
    assert configured.model == "test-model-b"

    try:
        FakeOllama(["test-model-a", "test-model-b"])
    except ModelSelectionError:
        pass
    else:
        raise AssertionError("Multiple models without a selection must fail.")

    print("Ollama service test passed.")


if __name__ == "__main__":
    main()
