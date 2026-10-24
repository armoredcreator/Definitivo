from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from ArmoredSync.service import TelegramSource


class FakeReader:
    def __init__(self, message):
        self.client = SimpleNamespace(get_messages=self.get_messages)
        self.message = message
        self.connect_calls = 0
        self.disconnect_calls = 0

    async def connect(self):
        self.connect_calls += 1

    async def disconnect(self):
        self.disconnect_calls += 1

    async def get_messages(self, source, ids):
        return self.message


def make_source(tmp_path: Path, monkeypatch, attempts="3"):
    monkeypatch.setenv("ARMORED_SYNC_SOURCE", "-1002698134896")
    monkeypatch.setenv("ARMORED_SYNC_DOWNLOAD_ATTEMPTS", attempts)
    monkeypatch.setattr("ArmoredSync.service.asyncio.sleep", no_sleep)
    source = TelegramSource.__new__(TelegramSource)
    source.source = "-1002698134896"
    source.source_id = "-1002698134896"
    source.root = tmp_path
    source.reader = FakeReader(SimpleNamespace(video=True, id=104718))
    return source


async def no_sleep(_seconds):
    return None


def test_transient_request_failure_retries_and_succeeds(tmp_path, monkeypatch):
    source = make_source(tmp_path, monkeypatch)
    target = tmp_path / "original.mp4"
    calls = 0

    async def download(_message, path):
        nonlocal calls
        calls += 1
        path.write_bytes(b"partial")
        if calls == 1:
            raise ValueError("Request was unsuccessful 6 time(s)")
        path.write_bytes(b"complete")

    source._download_to = download
    asyncio.run(source.materialize_candidate_async("104718", target))

    assert calls == 2
    assert target.read_bytes() == b"complete"
    assert source.reader.connect_calls == 2
    assert source.reader.disconnect_calls == 1


def test_persistent_request_failure_stops_after_bounded_attempts(tmp_path, monkeypatch):
    source = make_source(tmp_path, monkeypatch, attempts="2")
    target = tmp_path / "original.mp4"
    calls = 0

    async def download(_message, path):
        nonlocal calls
        calls += 1
        path.write_bytes(b"partial")
        raise ValueError("Request was unsuccessful 6 time(s)")

    source._download_to = download
    with pytest.raises(ValueError, match="Request was unsuccessful 6 time"):
        asyncio.run(source.materialize_candidate_async("104718", target))

    assert calls == 2
    assert not target.exists()
    assert source.reader.disconnect_calls == 1


def test_missing_video_is_not_retried(tmp_path, monkeypatch):
    source = make_source(tmp_path, monkeypatch)
    source.reader.message = None
    target = tmp_path / "original.mp4"

    with pytest.raises(RuntimeError, match="historical-video-not-found"):
        asyncio.run(source.materialize_candidate_async("104718", target))

    assert source.reader.connect_calls == 1
    assert source.reader.disconnect_calls == 0
    assert not target.exists()
