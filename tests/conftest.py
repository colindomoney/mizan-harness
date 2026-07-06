from types import SimpleNamespace


class FakeCompletions:
    """Stands in for client.chat.completions; records requests, can fail on cue."""

    def __init__(
        self,
        *,
        reply: str = "hello",
        error: Exception | None = None,
        errors: list[Exception] | None = None,
    ) -> None:
        self.reply = reply
        self.error = error
        self.errors = errors or []  # raised one by one, then calls succeed
        self.calls = 0
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self.errors:
            raise self.errors.pop(0)
        if self.error:
            raise self.error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))],
            model=kwargs["model"],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=34),
            model_dump=lambda: {"id": "cmpl-fake", "model": kwargs["model"]},
        )


def fake_client(completions: FakeCompletions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))
