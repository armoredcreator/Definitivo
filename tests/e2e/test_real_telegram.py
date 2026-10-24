from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

from armored_core.coordinator import Coordinator
from armored_core.models import State
from armored_core.routing import load_routes, validate_contract_routes


ROUTE_TOPIC_BY_SOURCE_ID = {
    "-1003788989075": 228,
    "-1002698134896": 1160,
    "-1002039708059": 1327,
}


class RealTelegramE2ETests(unittest.TestCase):
    """Opt-in real Telegram -> Vision -> Studio -> Hub -> Telegram test."""

    def test_real_telegram_full_pipeline(self):
        if os.getenv("ARMORED_REAL_TELEGRAM_E2E", "0") != "1":
            self.skipTest("ARMORED_REAL_TELEGRAM_E2E=1 required")
        if os.getenv("ARMORED_REAL_PUBLICATION_AUTHORIZED", "0") != "1":
            self.skipTest("explicit real-publication authorization required")

        authorized_topic = (os.getenv("ARMORED_REAL_PUBLICATION_TOPIC_ID") or "").strip()
        if authorized_topic not in {str(topic) for topic in ROUTE_TOPIC_BY_SOURCE_ID.values()}:
            self.fail(
                "ARMORED_REAL_PUBLICATION_TOPIC_ID must name one of the three "
                "contract-authorized destinations"
            )

        previous = {
            name: os.environ.get(name)
            for name in (
                "ARMORED_REAL_TELEGRAM",
                "ARMORED_HUB_DRY_RUN",
                "ARMORED_HUB_VERIFY_TELEGRAM",
                "ARMORED_STUDIO_FORCE_COPY",
            )
        }
        os.environ["ARMORED_REAL_TELEGRAM"] = "1"
        os.environ["ARMORED_HUB_DRY_RUN"] = "0"
        # Recovery of an unresolved publication must verify Telegram before
        # deciding whether a resend is safe.
        os.environ["ARMORED_HUB_VERIFY_TELEGRAM"] = "1"
        root = Path.cwd()

        coordinator = Coordinator.build(root)

        required = (
            "TELEGRAM_API_ID",
            "TELEGRAM_API_HASH",
            "ARMORED_CREATOR_BOT_TOKEN",
        )
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            coordinator.close()
            self.fail("Missing real-E2E environment variables: " + ", ".join(missing))

        source = coordinator.source
        item_id = None

        try:
            item_id = asyncio.run(coordinator.ingest_once_async())
            self.assertIsNotNone(item_id, "Telegram source returned no eligible video")

            current = coordinator.db.get(str(item_id))
            routes = validate_contract_routes(load_routes())
            route = next(
                (candidate for candidate in routes if candidate.source.source_id == str(current.source_id)),
                None,
            )
            self.assertIsNotNone(
                route,
                f"Source {current.source_id!r} is outside the Definitivo route contract",
            )
            # The ingested topic belongs to the source forum. The authorized
            # topic belongs to the Hub destination; validate each independently.
            self.assertIsNotNone(current.topic_id, "Telegram source topic was not persisted")
            self.assertGreater(int(current.topic_id), 0)
            self.assertEqual(int(route.hub.topic_id), int(authorized_topic))
            if current.state == State.FAILED:
                coordinator.recover(str(item_id))
            else:
                coordinator.run(str(item_id))
            item = coordinator.db.get(str(item_id))

            self.assertEqual(item.state, State.PUBLISHED)
            self.assertTrue(item.original_path.is_file())
            self.assertTrue(item.cleanup_completed)

            publication = coordinator.db.publication(str(item_id))
            self.assertIsNotNone(publication)
            self.assertEqual(int(publication["confirmed"]), 1)
            self.assertTrue(str(publication["published_message_id"]).isdigit())
            self.assertEqual(str(publication["destination_chat_id"]), str(route.hub.chat_id))
            self.assertEqual(int(publication["destination_topic_id"]), int(route.hub.topic_id))

            before = publication["published_message_id"]
            coordinator.run(str(item_id))
            after = coordinator.db.publication(str(item_id))["published_message_id"]
            self.assertEqual(after, before)

            files = [path.name for path in item.workspace.iterdir()]
            self.assertEqual(
                set(files),
                {item.original_path.name, item.result_path.name},
            )
        finally:
            reader = getattr(source, "reader", None)
            if reader is not None:
                asyncio.run(reader.disconnect())
            coordinator.close()
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
