from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ArmoredSync.service import TelegramSource
from armored_core.database import Database
from armored_core.coordinator import Coordinator
from armored_core.models import State
from armored_core.preflight import _archived_item_count
from armored_core.routing import RouteConfig, SourceConfig, HubConfig, validate_contract_routes
from armored_core.services import IngestMessage, SyncService
from armored_core.storage import Storage


def test_album_with_one_known_url_keeps_every_video_identity(tmp_path: Path):
    db = Database(tmp_path / "items.sqlite3")
    url = "https://shopee.com.br/product/known"
    db.reserve_item("old", source_id="source-a", original_url=url)
    source = TelegramSource(
        tmp_path, SimpleNamespace(), db=db, source="-1001", source_id="source-a"
    )
    album = [
        SimpleNamespace(id=11, video=object(), message=url, entities=[], grouped_id=444),
        SimpleNamespace(id=12, video=object(), message="", entities=[], grouped_id=444),
    ]

    candidates = source._grouped_candidates(album, 7, "source topic")

    assert [candidate[0] for candidate in candidates] == [11, 12]
    assert [candidate[4] for candidate in candidates] == [url, url]


def test_album_identity_and_grouped_id_are_persisted_without_materialization(tmp_path: Path):
    storage = Storage(tmp_path)
    db = Database(storage.database / "items.sqlite3")
    sync = SyncService(db, storage)
    first = sync.reserve_message(IngestMessage(
        telegram_message_id="11", source_id="source-a", topic_id=7,
        grouped_id=444, original_url="https://shopee.com.br/product/album",
        materialize=lambda _path: None,
    ))
    second = sync.reserve_message(IngestMessage(
        telegram_message_id="12", source_id="source-a", topic_id=7,
        grouped_id=444, original_url="https://shopee.com.br/product/album",
        materialize=lambda _path: None,
    ))

    assert db.get(first).grouped_id == 444
    assert db.get(second).grouped_id == 444
    assert db.get(second).state == State.DUPLICATE
    assert db.get(second).duplicate_of_content_id == first
    assert not storage._workspace_path(second, "source-a").exists()


def test_preflight_archive_count_accepts_uncompacted_database():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE items(content_id TEXT)")

    assert _archived_item_count(connection) == 0

    connection.execute("CREATE TABLE reconciliation_archived_items(content_id TEXT)")
    connection.execute("INSERT INTO reconciliation_archived_items VALUES ('archived-1')")
    assert _archived_item_count(connection) == 1


def test_shared_route_validator_enforces_contract_associations():
    good = (
        RouteConfig(SourceConfig("one", "-1003788989075", "source-one"), HubConfig("hub1", "-1004341972306", 228)),
        RouteConfig(SourceConfig("two", "-1002698134896", "source-two"), HubConfig("hub2", "-1004341972306", 1160)),
        RouteConfig(SourceConfig("three", "-1002039708059", "source-three"), HubConfig("hub3", "-1004341972306", 1327)),
    )
    assert validate_contract_routes(good) == good
    wrong = good[:-1] + (
        RouteConfig(good[2].source, HubConfig("hub3", "-1004341972306", 228)),
    )
    with pytest.raises(RuntimeError, match="destino Hub|destinos Hub"):
        validate_contract_routes(wrong)


def test_coordinator_build_rejects_routes_that_bypass_cli_validation(tmp_path: Path):
    invalid = (
        RouteConfig(SourceConfig("one", "-1003788989075", "source-one"), HubConfig("hub1", "-1004341972306", 228)),
        RouteConfig(SourceConfig("two", "-1002698134896", "source-two"), HubConfig("hub2", "-1004341972306", 1160)),
        RouteConfig(SourceConfig("three", "-1002039708059", "source-three"), HubConfig("hub3", "-1004341972306", 228)),
    )
    with patch("armored_core.coordinator.load_routes", return_value=invalid):
        with pytest.raises(RuntimeError, match="destino Hub|destinos Hub"):
            Coordinator.build(tmp_path)
