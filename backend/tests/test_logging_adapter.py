"""get_logger() must honor the stdlib %-style calls used across the codebase."""

import pytest
from loguru import logger as loguru_logger

from api.core.logging_config import get_logger


@pytest.fixture
def captured():
    records = []
    sink_id = loguru_logger.add(lambda m: records.append(m.record), format="{message}", level="DEBUG")
    yield records
    loguru_logger.remove(sink_id)


def test_percent_args_are_interpolated(captured) -> None:
    get_logger("t").info("created %s (prefix=%s)", "RET-v4", "/api/v1")
    assert captured[-1]["message"] == "created RET-v4 (prefix=/api/v1)"


def test_brace_style_and_structured_fields_still_work(captured) -> None:
    log = get_logger("t")
    log.info("user {user} logged in", user="demo")
    assert captured[-1]["message"] == "user demo logged in"
    assert captured[-1]["extra"]["user"] == "demo"
    log.warning("payload {raw} from %s", "client", path="/x")
    assert captured[-1]["message"] == "payload {raw} from client"
    assert captured[-1]["extra"]["path"] == "/x"


def test_exception_keeps_traceback_and_caller(captured) -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        get_logger("t").exception("failed for %s", "job-7")
    record = captured[-1]
    assert record["message"] == "failed for job-7"
    assert record["exception"] is not None
    assert record["function"] == "test_exception_keeps_traceback_and_caller"


def test_bind_returns_adapter(captured) -> None:
    get_logger("t").bind(corr_id="abc").error("status %d", 500)
    assert captured[-1]["message"] == "status 500"
    assert captured[-1]["extra"]["corr_id"] == "abc"
