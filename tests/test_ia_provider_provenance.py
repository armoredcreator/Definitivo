import pytest

from ArmoredIA.service import ArmoredIA
from ArmoredIA.caption.generator import CaptionGenerationError
from armored_core.coordinator import Coordinator
from armored_core.database import Database
from armored_core.models import State
from armored_core.services import SyncService
from armored_core.storage import Storage


@pytest.mark.parametrize("configured_provider", ["ollama", "gemini", "unknown"])
def test_pipeline_does_not_invent_caption_for_unknown_product_category(
    tmp_path, monkeypatch, configured_provider,
):
    monkeypatch.setenv("ARMORED_IA_PROVIDER", configured_provider)
    monkeypatch.setenv("ARMORED_IA_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    storage = Storage(tmp_path)
    db = Database(storage.database / "test.sqlite3")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"synthetic original")
    item_id = SyncService(db, storage).ingest(source, "1", source_id="synthetic")
    db.set_vision(
        item_id,
        "Produto para casa",
        "https://affiliate.invalid/example",
        ia_context={
            "productName": "Produto para casa",
            "category": "casa",
            "usage": "ambiente acolhedor",
            "shopId": "10",
            "itemId": "20",
        },
    )
    ia = ArmoredIA()
    assert ia.caption_generator.provider is None
    assert ia.provider_configuration() == {
        "provider": "local",
        "model": "deterministic-caption-rules",
    }
    coordinator = Coordinator(db, storage, None, None, None, ia=ia)
    try:
        with pytest.raises(CaptionGenerationError):
            coordinator.pipeline.run(item_id, stop_after_ia=True)
        assert db.get(item_id).publication_caption is None
        assert db.publication(item_id) is None
    finally:
        coordinator.close()


def test_title_only_item_gets_a_local_caption_and_zero_provider_requests(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("ARMORED_IA_PROVIDER", "ollama")
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "0")
    storage = Storage(tmp_path)
    db = Database(storage.database / "test.sqlite3")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"synthetic original")
    item_id = SyncService(db, storage).ingest(source, "2", source_id="synthetic")
    title = "Esfoliante Corporal Hidratante Banho Estrias 150g Cicatribem"
    db.set_vision(
        item_id, title, "https://affiliate.invalid/example",
        ia_context={"productName": title},
    )
    ia = ArmoredIA()
    coordinator = Coordinator(db, storage, None, None, None, ia=ia)
    try:
        coordinator.pipeline.run(item_id, stop_after_ia=True)
        assert db.get(item_id).state is State.SPEECH
        assert db.get(item_id).publication_caption == (
            "🧡 Esfoliação corporal no banho\n#esfoliante"
        )
        receipt = db.conn.execute(
            "SELECT provider,model,status,request_count FROM ia_generation_attempts "
            "WHERE content_id=?", (item_id,),
        ).fetchone()
        assert tuple(receipt) == (
            "local", "deterministic-caption-rules", "COMPLETE", 0,
        )
    finally:
        coordinator.close()
