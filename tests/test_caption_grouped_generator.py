from __future__ import annotations

import json

import pytest
import requests

from ArmoredIA.caption.grouped import CaptionGroupGenerator
from ArmoredIA.providers.base import AIProviderError
from ArmoredIA.providers.gemini_grouped import GeminiGroupedProvider


class Response:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self.payload = payload
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload

    def close(self):
        self.closed = True


def grouped_payload(rows):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps({"products": rows})}]}}]}


def test_grouped_provider_sends_one_request_and_keeps_product_candidates_separate(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    response = Response(grouped_payload([
        {"id": "watch", "captions": ["Ilha dinâmica #smartwatch"]},
        {"id": "peeler", "captions": ["Parece até um apontador #descascador"]},
    ]))
    calls = []

    def requester(*args, **kwargs):
        calls.append((args, kwargs))
        return response

    provider = GeminiGroupedProvider(requester=requester, sleeper=lambda _delay: None)
    result = provider.generate_candidates_for_products("caption", {
        "watch": {"productName": "Smartwatch Ilha Dinâmica"},
        "peeler": {"productName": "Descascador de Legumes Apontador"},
    }, 1)

    assert len(calls) == 1
    assert result == {
        "watch": ["Ilha dinâmica #smartwatch"],
        "peeler": ["Parece até um apontador #descascador"],
    }
    body = calls[0][1]["json"]
    prompt = body["contents"][0]["parts"][0]["text"]
    assert '"id": "watch"' in prompt
    assert '"id": "peeler"' in prompt
    assert response.closed


@pytest.mark.parametrize("rows", [
    [{"id": "watch", "captions": ["x"]}],
    [
        {"id": "watch", "captions": ["x"]},
        {"id": "watch", "captions": ["y"]},
    ],
    [
        {"id": "watch", "captions": ["x"]},
        {"id": "other", "captions": ["y"]},
    ],
])
def test_grouped_provider_rejects_missing_duplicate_or_foreign_products(monkeypatch, rows):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    provider = GeminiGroupedProvider(
        requester=lambda *_args, **_kwargs: Response(grouped_payload(rows)),
        sleeper=lambda _delay: None,
    )

    with pytest.raises(AIProviderError):
        provider.generate_candidates_for_products(
            "caption", {"watch": {"productName": "Smartwatch"}, "peeler": {"productName": "Descascador"}}, 1,
        )


def test_group_generator_runs_local_policy_independently_for_each_product():
    class Provider:
        last_attempts = [{"attempt": 1, "status": "SUCCESS"}]

        def generate_candidates_for_products(self, task, products, limit):
            assert task == "caption"
            assert limit == 10
            assert set(products) == {"watch", "peeler"}
            return {
                "watch": ["Ilha dinâmica #smartwatch", "Oferta imperdível #smartwatch"],
                "peeler": ["Parece até um apontador #descascador", "Legumes perfeitos #legumes"],
            }

    result = CaptionGroupGenerator(provider=Provider()).generate_with_evidence({
        "watch": {"productName": "Smartwatch W29 Ilha Dinâmica"},
        "peeler": {"productName": "Descascador de Legumes Apontador"},
    })

    assert result.provider_requests == 1
    assert len(result.items) == 2
    assert result.items[0].selection is not None
    assert result.items[0].selection.caption == "🧡 Ilha dinâmica\n#smartwatch"
    assert result.items[0].candidates[1].policy_valid is False
    assert result.items[1].selection is not None
    assert result.items[1].selection.caption == "🧡 Parece até um apontador\n#descascador"
