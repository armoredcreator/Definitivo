from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from ArmoredHub.service import ArmoredHub
from armored_core.database import Database
from armored_core.models import Item, State


def _confirmed_db(path: Path) -> tuple[Database, str]:
    db = Database(path)
    content_id = "-1003788989075_91"
    db.conn.execute(
        "INSERT INTO items(content_id,telegram_message_id,source_id,state,original_path,"
        "affiliate_name,affiliate_url,publication_caption,affiliate_urls_json,ia_context_json) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            content_id, "91", "-1003788989075", "PUBLISHED", str(path.parent / "91.mp4"),
            "Chinelo feminino uso casual", "https://s.shopee.com.br/abc", "Legenda antiga",
            '["https://s.shopee.com.br/abc"]',
            '{"productName":"Chinelo feminino uso casual","usage":"uso casual"}',
        ),
    )
    db.conn.execute(
        "INSERT INTO publications(content_id,idempotency_key,published_message_id,confirmed,"
        "verification_status,destination_chat_id,destination_topic_id) "
        "VALUES(?,?,?,?,?,?,?)",
        (content_id, "key-91", "501", 1, "CONFIRMED", "-1004341972306", 228),
    )
    db.conn.commit()
    return db, content_id


def test_published_caption_edit_requires_confirmed_receipt_and_keeps_published_state(tmp_path):
    db, content_id = _confirmed_db(tmp_path / "captions.sqlite3")
    try:
        prepared = db.prepare_published_caption_edit(
            batch_id="caption-test",
            item_id=content_id,
            published_message_id="501",
            destination_chat_id="-1004341972306",
            destination_topic_id=228,
            previous_caption="Legenda antiga\n\nhttps://s.shopee.com.br/abc",
            selected_caption="🧡 Uso casual\n#chinelo",
            final_caption="🧡 Uso casual\n#chinelo\n\nhttps://s.shopee.com.br/abc",
            provider="ollama",
            model="qwen2.5:3b",
            generation_batch_id="generation-91",
        )
        db.set_published_caption_edit_status(prepared["edit_id"], "SENDING")
        db.set_published_caption_edit_status(prepared["edit_id"], "CONFIRMED")
        assert db.get(content_id).state is State.PUBLISHED
        assert db.get(content_id).publication_caption == "🧡 Uso casual\n#chinelo"
        receipt = db.publication(content_id)
        assert receipt["published_message_id"] == "501"
        assert receipt["verification_status"] == "CONFIRMED"
    finally:
        db.close()


def test_published_caption_edit_rejects_wrong_receipt_route(tmp_path):
    db, content_id = _confirmed_db(tmp_path / "captions.sqlite3")
    try:
        with pytest.raises(RuntimeError, match="caption-edit-receipt-mismatch"):
            db.prepare_published_caption_edit(
                batch_id="caption-test",
                item_id=content_id,
                published_message_id="501",
                destination_chat_id="-1004341972306",
                destination_topic_id=1327,
                previous_caption="old",
                selected_caption="🧡 Uso casual\n#chinelo",
                final_caption="new",
                provider="ollama",
                model="qwen2.5:3b",
                generation_batch_id="generation-91",
            )
    finally:
        db.close()


def test_hub_edits_only_confirmed_message_caption_and_preserves_route_and_video(monkeypatch, tmp_path):
    item = Item(
        content_id="-1003788989075_91",
        telegram_message_id="91",
        state=State.PUBLISHED,
        workspace=tmp_path,
        original_path=tmp_path / "91.mp4",
        working_path=None,
        result_path=None,
        affiliate_name="Chinelo feminino uso casual",
        affiliate_url="https://s.shopee.com.br/abc",
        source_id="-1003788989075",
        publication_caption="Legenda antiga",
        affiliate_urls=("https://s.shopee.com.br/abc",),
        ia_context={"productName": "Chinelo feminino uso casual", "usage": "uso casual"},
    )
    publication = {
        "confirmed": 1,
        "verification_status": "CONFIRMED",
        "published_message_id": "501",
        "destination_chat_id": "-1004341972306",
        "destination_topic_id": 228,
    }

    class FakeDB:
        path = tmp_path / "captions.sqlite3"

        def get(self, _content_id):
            return item

        def publication(self, _content_id):
            return publication

    sent = {}

    class FakeBot:
        def __init__(self, **_kwargs):
            pass

        async def edit_message_caption(self, **kwargs):
            sent.update(kwargs)
            return SimpleNamespace(
                chat=SimpleNamespace(id=-1004341972306),
                message_id=501,
                message_thread_id=228,
                caption=kwargs["caption"],
                video=object(),
                document=None,
            )

        async def shutdown(self):
            return None

    import telegram

    monkeypatch.setattr(telegram, "Bot", FakeBot)
    monkeypatch.setenv("ARMORED_CREATOR_BOT_TOKEN", "test-token")
    monkeypatch.setenv("ARMORED_TELEGRAM_BOT_API_URL", "http://127.0.0.1:8081/bot")
    monkeypatch.setenv("ARMORED_TELEGRAM_BOT_API_FILE_URL", "http://127.0.0.1:8081/file/bot")
    hub = ArmoredHub(tmp_path, db=FakeDB())
    hub._assert_not_quarantined = lambda _item: None
    hub._assert_test_destination_lock = lambda _item: None
    hub._run_async = lambda coro: asyncio.run(coro)

    result = hub.edit_confirmed_caption(
        item.content_id,
        "🧡 Uso casual\n#chinelo",
        affiliate_links=("https://s.shopee.com.br/abc",),
    )
    assert sent["chat_id"] == -1004341972306
    assert sent["message_id"] == 501
    assert "https://s.shopee.com.br/abc" in sent["caption"]
    assert result["topic_id"] == 228
    assert result["caption"] == sent["caption"]


def test_hub_refuses_to_edit_unconfirmed_publication(monkeypatch, tmp_path):
    item = Item(
        content_id="-1003788989075_91", telegram_message_id="91", state=State.PUBLISHED,
        workspace=tmp_path, original_path=tmp_path / "91.mp4", working_path=None,
        result_path=None, affiliate_name="Chinelo feminino uso casual",
        affiliate_url="https://s.shopee.com.br/abc", source_id="-1003788989075",
        ia_context={"productName": "Chinelo feminino uso casual"},
    )

    class FakeDB:
        path = tmp_path / "captions.sqlite3"
        def get(self, _content_id):
            return item
        def publication(self, _content_id):
            return {"confirmed": 0, "verification_status": "PENDING"}

    hub = ArmoredHub(tmp_path, db=FakeDB())
    with pytest.raises(RuntimeError, match="confirmed-publication-receipt"):
        hub.edit_confirmed_caption(item.content_id, "🧡 Uso casual\n#chinelo")


def test_hub_accepts_only_exact_local_title_rule_caption(monkeypatch, tmp_path):
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    title = "Pantufa 3D Garra Sulley Azul Rosa Grande Cano Longo Quentinha"
    item = Item(
        content_id="-1003788989075_92", telegram_message_id="92", state=State.PUBLISHED,
        workspace=tmp_path, original_path=tmp_path / "92.mp4", working_path=None,
        result_path=None, affiliate_name=title,
        affiliate_url="https://s.shopee.com.br/abc", source_id="-1003788989075",
        ia_context={"productName": title},
    )

    caption = "🧡 Pantufa com cano longo\n#pantufa"
    assert ArmoredHub._validated_caption(item, caption) == caption

    item.ia_context["__title_rule_caption_main"] = "Abertura inventada"
    with pytest.raises(RuntimeError, match="Policy ArmoredIA"):
        ArmoredHub._validated_caption(item, "🧡 Abertura inventada\n#pantufa")
