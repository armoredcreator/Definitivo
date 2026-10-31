from __future__ import annotations

import json
import re

import pytest
import requests

from ArmoredIA.providers.base import AIProviderError
from ArmoredIA.providers.gemini import GeminiProvider
from ArmoredIA.providers.ollama import OllamaProvider
from ArmoredIA.caption.policy import CaptionPolicyError, normalize_caption, validate_caption


class _Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return self.payload


def test_ollama_provider_returns_structured_caption_candidates(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_OLLAMA_URL", "http://localhost:11434/")
    monkeypatch.setenv("ARMORED_IA_OLLAMA_MODEL", "qwen2.5:1.5b")
    monkeypatch.delenv("ARMORED_IA_OLLAMA_TEMPERATURE", raising=False)
    calls = []

    def requester(url, **kwargs):
        calls.append((url, kwargs))
        return _Response({"response": json.dumps({
            "captions": ["Cantinho aconchegante\n#decor #casa", "Luz suave\n#quarto"]
        })})

    provider = OllamaProvider(requester=requester)
    result = provider.generate_candidates("caption", {"productName": "Copo Térmico de Café"}, 2)

    assert result == ["Cantinho aconchegante\n#decor #casa", "Luz suave\n#quarto"]
    assert calls[0][0] == "http://localhost:11434/api/generate"
    assert calls[0][1]["json"]["model"] == "qwen2.5:1.5b"
    assert calls[0][1]["json"]["stream"] is False
    assert calls[0][1]["json"]["options"]["temperature"] == 0.1
    assert calls[0][1]["json"]["options"]["repeat_penalty"] == 1.15
    schema = calls[0][1]["json"]["format"]
    assert schema["type"] == "object"
    assert schema["properties"]["captions"]["items"]["type"] == "string"
    assert schema["properties"]["captions"]["minItems"] == 2
    assert schema["properties"]["captions"]["maxItems"] == 2
    caption_pattern = schema["properties"]["captions"]["items"]["pattern"]
    assert re.fullmatch(caption_pattern, "Café quentinho")
    assert re.fullmatch(caption_pattern, "O café está quentinho")
    assert not re.fullmatch(caption_pattern, "Modelo G2 a G3")
    assert not re.fullmatch(caption_pattern, "Muito além do que você espera")
    assert "retorne exatamente 2 opções distintas" in calls[0][1]["json"]["prompt"].casefold()
    assert '"titulo_do_produto_vision":"Copo Térmico de Café"' in calls[0][1]["json"]["prompt"]
    assert "use o título da vision como principal fonte" in calls[0][1]["json"]["prompt"].casefold()
    assert "não copie o título" in calls[0][1]["json"]["prompt"].casefold()


def test_ollama_keeps_raw_duplicate_candidates_for_audit_but_dedupes_selection():
    payload = {"response": json.dumps({"captions": [
        "Café quentinho", "Café quentinho", "Display digital",
    ]})}
    provider = OllamaProvider(requester=lambda *_args, **_kwargs: _Response(payload))

    selected_candidates = provider.generate_candidates("caption", {}, 3)

    assert selected_candidates == ["Café quentinho", "Display digital"]
    assert provider.last_raw_candidates == [
        "Café quentinho", "Café quentinho", "Display digital",
    ]
    assert provider.last_candidate_count == 2


def test_ollama_provider_rejects_non_caption_task():
    with pytest.raises(AIProviderError, match="task não suportada"):
        OllamaProvider(requester=lambda *_args, **_kwargs: None).generate_candidates("vision", {}, 3)


def test_ollama_provider_rejects_malformed_response():
    provider = OllamaProvider(requester=lambda *_args, **_kwargs: _Response({"response": "not json"}))
    with pytest.raises(AIProviderError, match="JSON estruturado"):
        provider.generate_candidates("caption", {}, 2)


def test_caption_generator_provider_is_configurable(monkeypatch):
    from ArmoredIA.caption.generator import CaptionGenerator
    from ArmoredIA.caption.selector import CaptionGenerationError

    monkeypatch.delenv("ARMORED_IA_PROVIDER", raising=False)
    assert CaptionGenerator().provider is None

    monkeypatch.setenv("ARMORED_IA_PROVIDER", "gemini")
    assert CaptionGenerator().provider is None

    monkeypatch.setenv("ARMORED_IA_PROVIDER", "ollama")
    assert CaptionGenerator().provider is None

    monkeypatch.setenv("ARMORED_IA_PROVIDER", "unknown")
    with pytest.raises(CaptionGenerationError, match="geração operacional.*local"):
        CaptionGenerator().generate_with_evidence({}, force_provider=True)


def test_ollama_generator_defaults_to_ten_candidates_in_one_request(monkeypatch):
    from ArmoredIA.caption.generator import CaptionGenerator

    monkeypatch.setenv("ARMORED_IA_PROVIDER", "ollama")
    monkeypatch.setenv("ARMORED_IA_MAX_CANDIDATES", "10")
    monkeypatch.delenv("ARMORED_IA_OLLAMA_MAX_CANDIDATES", raising=False)
    calls = []
    response_body = json.dumps({"captions": [
        f"{text} #chinelo"
        for text in (
            "Uso casual", "Estilo casual", "Visual casual", "Para passeios", "Dia a dia",
            "Chinelo casual", "Look para passeios", "Um jeito casual", "Nos passeios",
            "Calçado para passeio",
        )
    ]})

    def requester(_url, *, json, timeout):
        calls.append(json)
        return _Response({"response": response_body})

    generator = CaptionGenerator(provider=OllamaProvider(requester=requester))
    result = generator.generate_with_evidence({
        "productName": "Chinelo feminino com detalhe em strass",
        "category": "calçados",
        "usage": "uso casual",
    }, force_provider=True)
    assert result.caption == "🧡 Uso casual\n#chinelo"
    assert calls[0]["format"]["type"] == "object"
    assert "retorne exatamente 10 opções distintas" in calls[0]["prompt"].casefold()
    assert len(calls) == 1
    assert calls[0]["format"]["properties"]["captions"]["minItems"] == 10
    assert len(calls) == 1
    assert generator.provider.last_request_count == 1
    assert generator.provider.last_candidate_count == 10
    assert len(result.provider_candidate_batches) == 1
    assert len(result.provider_candidate_batches[0]) == 10
    assert result.provider_candidate_batches[0][0] == "Uso casual #chinelo"
    assert calls[0]["format"]["properties"]["captions"]["maxItems"] == 10
    assert "não inclua coração, hashtag" in calls[0]["prompt"]


def test_ollama_always_generates_ten_candidates_before_local_selection(monkeypatch):
    from ArmoredIA.caption.generator import CaptionGenerator

    monkeypatch.setenv("ARMORED_IA_OLLAMA_MAX_CANDIDATES", "10")
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")

    class Provider:
        calls = 0

        @staticmethod
        def configuration():
            return {"provider": "ollama"}

        def generate_candidates(self, _task, _context, limit):
            self.calls += 1
            assert limit == 10
            return [
                "A escrita pode ser apagada\n#caneta",
                "Caneta apagável\n#caneta",
                "Tinta apagável\n#caneta",
                "Escrita com apagador\n#caneta",
                "Caneta para escrita\n#caneta",
                "Traço que pode apagar\n#caneta",
                "Apague a escrita\n#caneta",
                "Uma escrita apagável\n#caneta",
                "Escrita em gel\n#caneta",
                "Caneta gel colorida\n#caneta",
            ]

    provider = Provider()
    result = CaptionGenerator(provider=provider).generate_with_evidence({
        "productName": "Caneta Gel Apagável",
    }, force_provider=True)
    assert provider.calls == 1
    assert len(result.evaluations) == 10


def test_ollama_generator_uses_ai_even_when_title_has_a_known_fact(monkeypatch):
    from ArmoredIA.caption.generator import CaptionGenerator

    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")

    class Provider:
        calls = 0

        @staticmethod
        def configuration():
            return {"provider": "ollama"}

        def generate_candidates(self, *_args, **_kwargs):
            self.calls += 1
            return ["Parece até um apontador\n#descascador #legumes"]

    provider = Provider()
    result = CaptionGenerator(provider=provider).generate_with_evidence({
        "productName": "Descascador de Legumes Apontador",
    }, force_provider=True)

    assert result.caption == "🧡 Parece até um apontador\n#descascador #legumes"
    assert result.provider_requests == 1
    assert provider.calls == 1
    assert result.evaluations[0].policy_valid


def test_ollama_format_retry_is_bounded_and_explains_the_repair(monkeypatch):
    from ArmoredIA.caption.generator import CaptionGenerator

    monkeypatch.setenv("ARMORED_IA_OLLAMA_FORMAT_RETRIES", "1")
    monkeypatch.setenv("ARMORED_IA_OLLAMA_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("ARMORED_IA_OLLAMA_MAX_CANDIDATES", "1")
    calls = []
    responses = iter([
        _Response({"response": "not-json"}),
        _Response({"response": json.dumps({"captions": [
            {"text": "Sala organizada", "hashtags": ["#sala"]}
        ]})}),
    ])

    def requester(_url, *, json, timeout):
        calls.append(json)
        return next(responses)

    generator = CaptionGenerator(provider=OllamaProvider(requester=requester))
    result = generator.generate_with_evidence({
        "productName": "Produto para casa", "description": "sala organizada",
    }, force_provider=True)
    assert result.caption == "🧡 Sala organizada\n#sala"
    assert len(calls) == 2
    assert "CORREÇÃO DE FORMATO" in calls[1]["prompt"]


def test_ollama_policy_feedback_excludes_rejected_title_phrase_on_retry(monkeypatch):
    from ArmoredIA.caption.generator import CaptionGenerator

    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "1")
    monkeypatch.setenv("ARMORED_IA_OLLAMA_MAX_CANDIDATES", "1")
    calls = []
    bodies = iter([
        {"response": json.dumps({"captions": [
            {"text": "Alça fina infantil", "hashtags": ["#alca"]}
        ]})},
        {"response": json.dumps({"captions": [
            {"text": "Tecido em algodão", "hashtags": ["#infantil"]}
        ]})},
    ])

    def requester(_url, *, json, timeout):
        calls.append(json)
        return _Response(next(bodies))

    generator = CaptionGenerator(provider=OllamaProvider(requester=requester))
    result = generator.generate_with_evidence({
        "productName": "Blusinha regata alça fina infantil menina algodão Malwee Kids",
        "category": "infantil",
    }, force_provider=True)
    assert result.caption == "🧡 Tecido em algodão\n#infantil"
    assert result.evaluations[-1].policy_valid
    assert len(calls) == 2
    assert "A Policy recusou a tentativa anterior" in calls[1]["prompt"]
    assert "Corrija sem acrescentar fatos" in calls[1]["prompt"]


def test_ollama_uses_simple_json_prompt_and_policy_grounds_content(monkeypatch):
    import json as json_module

    calls = []

    def requester(_url, *, json, timeout):
        calls.append(json)
        return _Response({"response": json_module.dumps({"captions": [
            {"text": "Bolsa bonita", "hashtags": ["#bolsa"]}
        ]})})

    provider = OllamaProvider(requester=requester)
    provider.generate_candidates("caption", {
        "productName": "Senhoras almoço bolsa computador portátil saco com compartimento almoço",
        "itemId": 27478503595,
        "shopId": 1415257023,
    }, 1)

    assert calls[0]["format"]["type"] == "object"
    prompt = calls[0]["prompt"].casefold()
    assert "use o título da vision como principal fonte" in prompt
    assert "pode mencionar o nome comum do produto se isso soar natural" in prompt
    assert "sem anúncio" in prompt
    assert '"fatos_confirmados"' in prompt
    assert "responda somente com um objeto json" in prompt
    assert '"titulo_do_produto_vision":"Senhoras almoço bolsa computador portátil saco com compartimento almoço"' in calls[0]["prompt"]
    assert "não transfira uma qualidade de um atributo para outro" in prompt
    assert "o título da vision como principal fonte" in prompt


def test_ollama_prompt_reproduces_compact_vision_fact_without_expansion():
    import json as json_module

    calls = []

    def requester(_url, *, json, timeout):
        calls.append(json)
        return _Response({"response": json_module.dumps({"captions": [
            {"text": "Divisórias modulares", "hashtags": ["#organizador"]}
        ]})})

    OllamaProvider(requester=requester).generate_candidates("caption", {
        "productName": "Organizador de Gaveta Modular com Divisórias",
        "category": "organizador",
        "description": "Divisórias modulares para gaveta.",
    }, 1)
    assert calls[0]["format"]["type"] == "object"
    assert '"fatos_confirmados":["Divisórias modulares"]' in calls[0]["prompt"]
    assert '"titulo_do_produto_vision":"Organizador de Gaveta Modular com Divisórias"' in calls[0]["prompt"]
    assert "o título da vision como principal fonte" in calls[0]["prompt"].casefold()
    assert "shopName" not in calls[0]["prompt"]
    assert "itemId" not in calls[0]["prompt"]
    assert "não invente benefício" in calls[0]["prompt"].casefold()
    caption_pattern = calls[0]["format"]["properties"]["captions"]["items"]["pattern"]
    assert re.fullmatch(caption_pattern, "Divisórias modulares")
    assert re.fullmatch(caption_pattern, "Divisórias muito eficazes")
    assert not re.fullmatch(caption_pattern, "Uma legenda com seis palavras agora")


def test_ollama_prompt_uses_previous_caption_only_to_avoid_repetition():
    import json as json_module

    calls = []

    def requester(_url, *, json, timeout):
        calls.append(json)
        return _Response({"response": json_module.dumps({"captions": ["Mangas variadas"]})})

    OllamaProvider(requester=requester).generate_candidates(
        "caption",
        {
            "productName": "Vestido longo com mangas variadas",
            "description": "Vestido longo com mangas variadas",
            "__previous_caption_to_avoid": "Leve e confortável",
        },
        1,
    )

    prompt = calls[0]["prompt"]
    assert "Legenda anterior" in prompt
    assert "Leve e confortável" in prompt
    assert "nunca como evidência do produto" in prompt
    assert "Evite copiar a frase inteira" in prompt
    assert "pode expressar naturalmente o mesmo fato confirmado" in prompt


def test_caption_policy_rejects_repeating_published_main_text():
    from ArmoredIA.caption.selector import CaptionSelector

    previous = "🧡 Parece até um apontador\n#descascador #legumes\nhttps://s.shopee.com.br/example"
    context = {
        "productName": "Descascador de Legumes Apontador",
        "__previous_caption_to_avoid": previous,
    }
    evaluations = CaptionSelector().evaluate(
        ["Parece até um apontador\n#descascador #cozinha"],
        product_name=context["productName"],
        product_context=context,
    )

    assert not evaluations[0].policy_valid
    assert evaluations[0].rejection_reason == "texto principal repete a legenda anterior"


def test_caption_policy_allows_a_new_frame_for_the_same_confirmed_comparison():
    from ArmoredIA.caption.selector import CaptionSelector

    context = {
        "productName": "Descascador de legumes apontador",
        "__vision_confirmed_facts": ["Parece até um apontador"],
        "__previous_caption_to_avoid": "🧡 Parece até um apontador\n#descascador #legumes",
    }
    evaluation = CaptionSelector().evaluate(
        ["É como um apontador\n#descascador"],
        product_name=context["productName"],
        product_context=context,
    )[0]

    assert evaluation.policy_valid


def test_caption_policy_rejects_near_duplicate_but_allows_a_new_vision_fact():
    from ArmoredIA.caption.selector import CaptionSelector

    previous = "🧡 Divisão isolada para refeições\n#bolsa"
    context = {
        "productName": "Bolsa para almoço com compartimento acolchoado",
        "__vision_confirmed_facts": ["Isolado acolchoado", "Compartimento de almoço"],
        "__previous_caption_to_avoid": previous,
    }
    evaluations = CaptionSelector().evaluate(
        [
            "🧡 Divisão para refeições\n#bolsa",
            "🧡 Compartimento acolchoado para almoço\n#bolsa",
        ],
        product_name=context["productName"],
        product_context=context,
    )

    assert not evaluations[0].policy_valid
    assert evaluations[0].rejection_reason == "texto principal muito semelhante à legenda anterior"
    assert evaluations[1].policy_valid

    ranking = CaptionSelector().evaluate(
        ["Acolchoado isolado", "Compartimento de almoço"],
        product_name=context["productName"],
        product_context=context,
    )
    selection, _marked = CaptionSelector().choose(ranking)
    assert selection.caption == "🧡 Compartimento de almoço\n#Bolsa"


def test_ollama_retry_avoids_previous_policy_rejections():
    import json as json_module

    calls = []

    def requester(_url, *, json, timeout):
        calls.append(json)
        return _Response({"response": json_module.dumps({"captions": ["Corações geométricos"]})})

    OllamaProvider(requester=requester).generate_candidates("caption", {
        "productName": "Brincos geométricos de coração",
        "description": "Coração geométrico",
        "__policy_retry_feedback": ["texto principal contém termo sem suporte no contexto Vision"],
        "__policy_retry_previous_candidates": ["🧡 Kit moderno #brincos", "Fio geométrico"],
    }, 3)

    prompt = calls[0]["prompt"]
    assert "A Policy recusou a tentativa anterior" in prompt
    assert "Não repita estas formulações recusadas" in prompt
    assert "Kit moderno" in prompt
    assert "Fio geométrico" in prompt
    assert "#brincos" not in prompt


def test_structured_model_fields_keep_hashtags_without_inventing_content():
    result = OllamaProvider._extract_candidates({"response": json.dumps({"captions": [
        {"text": "Cantinho sereno", "hashtags": ["#decor", "#casa"]}
    ]})}, 1)
    assert result == ["Cantinho sereno\n#decor #casa"]



def test_ollama_returns_invalid_candidate_for_shared_policy_to_reject(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_MAX_ATTEMPTS", "1")
    provider = OllamaProvider(
        requester=lambda *_args, **_kwargs: _Response({
            "response": json.dumps({"captions": ["Organizador de mesa simples"]})
        })
    )
    assert provider.generate_candidates("caption", {"productName": "Organizador"}, 1) == [
        "Organizador de mesa simples"
    ]


def test_ollama_returns_available_distinct_candidates_from_partial_batch(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_MAX_ATTEMPTS", "1")
    calls = []

    def requester(*_args, **_kwargs):
        calls.append(1)
        return _Response({
            "response": json.dumps({"captions": ["Mesa organizada ✨ #Escritório"]})
        })

    provider = OllamaProvider(
        requester=requester
    )
    assert provider.generate_candidates("caption", {"productName": "Organizador"}, 2) == [
        "Mesa organizada ✨ #Escritório"
    ]
    assert len(calls) == 1



def test_ollama_provider_preserves_raw_candidates_for_shared_policy(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_MAX_ATTEMPTS", "1")
    provider = OllamaProvider(
        requester=lambda *_args, **_kwargs: _Response({
            "response": json.dumps({
                "captions": ["Mesa organizada ✨🛍️ #Casa #casa"]
            })
        })
    )

    assert provider.generate_candidates("caption", {"productName": "Organizador"}, 1) == [
        "Mesa organizada ✨🛍️ #Casa #casa"
    ]



def test_ollama_provider_passes_corrupted_unicode_to_shared_policy(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_MAX_ATTEMPTS", "1")
    provider = OllamaProvider(
        requester=lambda *_args, **_kwargs: _Response({
            "response": json.dumps({
                "captions": ["Mesa organizada ?? #Casa"]
            })
        })
    )

    assert provider.generate_candidates("caption", {"productName": "Organizador"}, 1) == [
        "Mesa organizada ?? #Casa"
    ]



def test_ollama_default_model_uses_validated_local_qwen(monkeypatch):
    monkeypatch.delenv("ARMORED_IA_OLLAMA_MODEL", raising=False)
    monkeypatch.setenv("ARMORED_IA_MAX_ATTEMPTS", "1")
    calls = []

    def requester(url, **kwargs):
        calls.append(kwargs["json"]["model"])
        return _Response({"response": json.dumps({
            "captions": ["Mesa organizada #casa"]
        })})

    OllamaProvider(requester=requester).generate_candidates("caption", {}, 1)
    assert calls == ["qwen2.5:3b"]


def test_ollama_forwards_explicit_thinking_mode(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("ARMORED_IA_OLLAMA_THINK", "false")
    calls = []

    def requester(_url, **kwargs):
        calls.append(kwargs["json"])
        return _Response({"response": json.dumps({"captions": ["Mesa organizada #casa"]})})

    OllamaProvider(requester=requester).generate_candidates("caption", {}, 1)
    assert calls[0]["think"] is False


def test_ollama_caption_generator_ranks_policy_valid_candidates_by_vision_support(monkeypatch):
    import json as json_module

    from ArmoredIA.caption.generator import CaptionGenerator

    monkeypatch.setenv("ARMORED_IA_PROVIDER", "ollama")
    monkeypatch.setenv("ARMORED_IA_OLLAMA_MAX_CANDIDATES", "3")
    monkeypatch.delenv("ARMORED_IA_MAX_CANDIDATES", raising=False)
    calls = []

    def requester(_url, *, json, timeout):
        calls.append(json)
        return _Response({"response": json_module.dumps({"captions": [
            {"text": "Divisão para refeições", "hashtags": ["#bolsa"]},
            {"text": "Divisão isolada para refeições", "hashtags": ["#bolsa"]},
            {"text": "Bolsa de computador", "hashtags": ["#bolsa"]},
        ]})})

    generator = CaptionGenerator(provider=OllamaProvider(requester=requester))
    result = generator.generate_with_evidence({
        "productName": "Senhoras almoço bolsa computador portátil saco com compartimento almoço",
    }, force_provider=True)

    assert result.caption == "🧡 Divisão isolada para refeições\n#bolsa"
    assert result.selection.index == 2
    assert calls[0]["format"]["type"] == "object"
    assert "retorne exatamente 3 opções distintas" in calls[0]["prompt"].casefold()
    assert len(result.evaluations) == 3
    assert result.evaluations[2].policy_valid is False


@pytest.mark.parametrize(
    ("caption", "product_name", "expected"),
    [
        (
            "Café quentinho\n#café",
            "Xícara para café",
            "🧡 Café quentinho\n#café",
        ),
        (
            "O café que você merece\n#café",
            "Xícara para café",
            "🧡 O café que você merece\n#café",
        ),
    ],
)
def test_policy_accepts_owner_approved_short_editorial_captions(caption, product_name, expected):
    context = {"productName": product_name}
    normalized = normalize_caption(
        caption, product_name=product_name, product_context=context,
    ).caption
    assert validate_caption(
        normalized, product_name=product_name, product_context=context,
    ) == expected


def test_policy_rejects_incomplete_vision_supported_predicate():
    title = "Tênis casual detalhe lateral listra dupla"
    with pytest.raises(CaptionPolicyError, match="expressão vaga"):
        validate_caption(
            "🧡 Listras duplas na lateral são\n#tenis",
            product_name=title,
            product_context={"productName": title},
        )
