from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from ArmoredHub.service import ArmoredHub
from armored_core.database import Database
from armored_core.storage import Storage


class HubPreflightTests(unittest.TestCase):
    def test_unreachable_bot_api_does_not_enter_sent_unverified_window(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = Storage(root)
            db = Database(storage.database / "db.sqlite")
            try:
                original = storage.original("hub-preflight", original_url="https://example.invalid/item")
                original.parent.mkdir(parents=True, exist_ok=True)
                original.write_bytes(b"original")
                item_id = db.create_item(
                    "hub-preflight",
                    original,
                    original_url="https://example.invalid/item",
                )
                db.conn.execute(
                    "UPDATE items SET original_path=?, affiliate_name=?, affiliate_url=? WHERE content_id=?",
                    (str(original), "product", "https://example.invalid/final", item_id),
                )
                db.conn.commit()
                item = db.get(item_id)
                output = storage.result(item.content_id, item.affiliate_url, item.affiliate_name)
                output.write_bytes(b"rendered-video")
                db.set_result(item_id, output)
                item = db.get(item_id)
                db.publication_started(item_id)

                class NetworkError(Exception):
                    pass

                class TimedOut(NetworkError):
                    pass

                class FakeBot:
                    def __init__(self, **_kwargs):
                        pass

                    async def get_me(self):
                        raise NetworkError("local Bot API connection refused")

                    async def shutdown(self):
                        return None

                telegram = types.ModuleType("telegram")
                telegram.__path__ = []
                telegram.Bot = FakeBot
                errors = types.ModuleType("telegram.error")
                errors.NetworkError = NetworkError
                errors.TimedOut = TimedOut
                request = types.ModuleType("telegram.request")
                request.HTTPXRequest = lambda **_kwargs: object()

                hub = ArmoredHub(root, db)
                with patch.dict(
                    sys.modules,
                    {
                        "telegram": telegram,
                        "telegram.error": errors,
                        "telegram.request": request,
                    },
                ), patch.dict(
                    "os.environ",
                    {
                        "ARMORED_CREATOR_BOT_TOKEN": "test-token",
                        "ARMORED_CREATOR_GROUP_ID": "-100123",
                        "ARMORED_HUB_TOPIC_ID": "901",
                    },
                    clear=False,
                ), patch.object(hub, "_video_metadata", return_value=(720, 1280, 8)):
                    with self.assertRaisesRegex(RuntimeError, "envio do vídeo não foi iniciado"):
                        hub._publish_telegram(item, output)

                publication = db.publication(item_id)
                self.assertEqual(publication["verification_status"], "PENDING")
                self.assertEqual(publication["confirmed"], 0)
                self.assertIsNone(publication["published_message_id"])
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
