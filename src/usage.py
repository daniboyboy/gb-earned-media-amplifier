import threading
from contextlib import contextmanager

from src.pricing import cost_usd

_local = threading.local()


@contextmanager
def track_usage() -> dict:
    counter = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0}
    previous = getattr(_local, "counter", None)
    _local.counter = counter
    try:
        yield counter
    finally:
        _local.counter = previous


def record(completion, model: str) -> None:
    counter = getattr(_local, "counter", None)
    usage = getattr(completion, "usage", None)
    if counter is None or usage is None:
        return
    counter["input_tokens"] += usage.prompt_tokens
    counter["output_tokens"] += usage.completion_tokens
    counter["cost_usd"] = round(cost_usd(model, counter["input_tokens"], counter["output_tokens"]), 4)
    counter["calls"] += 1