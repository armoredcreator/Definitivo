import tempfile
import unittest
from pathlib import Path

from armored_core.database import Database
from armored_core.models import PublicationCheck, State
from armored_core.recovery import Recovery
from armored_core.services import PublicationResult
from armored_core.storage import Storage


class MustNotRunVision:
    def identify(self, item):
        raise AssertionError("VISION must not run when a durable result exists")


class MustNotRunStudio:
    def process(self, item):
        raise AssertionError("STUDIO must not run when a durable result exists")


class Publisher:
    def __init__(self):
        self.calls = 0

    def check_publication(self, item):
        return PublicationCheck.ABSENT

    def publish(self, item):
        self.calls += 1
        return PublicationResult(True, "recovered-publication")


class FailedResultRecoveryTests(unittest.TestCase):
    def test_failed_item_with_durable_result_skips_vision_and_studio(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = Storage(root)
            db = Database(storage.database / "armoredcreator.db")

            try:
                original = storage.original(
                    "failed-557",
                    original_url="https://example.invalid/source",
                )
                original.parent.mkdir(parents=True, exist_ok=True)
                original.write_bytes(b"ORIGINAL")
                item_id = db.create_item("failed-557", original)

                result = storage.result(item_id, "recover-final")
                result.write_bytes(b"FINAL")
                db.set_vision(
                    item_id,
                    "recover-final",
                    "https://example.invalid/affiliate",
                )
                db.set_result(item_id, result)
                db.fail(item_id, "simulated pre-recovery failure")

                publisher = Publisher()
                Recovery(
                    db,
                    storage,
                    MustNotRunVision(),
                    MustNotRunStudio(),
                    publisher,
                ).reconcile(item_id)

                row = db.get(item_id)
                # A durable render without a policy-approved caption is a
                # recoverable publication barrier, never a confirmed send.
                self.assertEqual(row.state, State.PUBLISHING)
                self.assertEqual(publisher.calls, 0)
                self.assertEqual(db.caption_recovery(item_id)["status"], "BLOCKED")

                # Recovery publishes the durable result and removes only
                # temporary derived artifacts; the published result is kept.
                self.assertTrue(result.is_file())
                self.assertTrue(original.exists())
                self.assertEqual(
                    {p.name for p in row.workspace.iterdir()},
                    {original.name, result.name},
                )

                events = [
                    r["new_state"]
                    for r in db.conn.execute(
                        "SELECT new_state FROM state_events "
                        "WHERE content_id=? ORDER BY id",
                        (item_id,),
                    ).fetchall()
                ]
                self.assertIn(State.RECOVERY.value, events)
                self.assertIn(State.PUBLISHING.value, events)
                self.assertNotIn(State.PUBLISHED.value, events)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
