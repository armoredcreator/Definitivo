from __future__ import annotations

from unittest.mock import Mock

from ArmoredVision.modules.v1.shopee_api import ShopeeAffiliateAPI


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_product_lookup_reuses_successful_result_in_client_lifetime(monkeypatch):
    api = ShopeeAffiliateAPI(app_id="app", secret_key="secret")
    response = _Response({
        "data": {
            "productOfferV2": {
                "nodes": [{
                    "shopId": "123",
                    "itemId": "456",
                    "productName": "Produto",
                    "productCatIds": [1001, 1002],
                    "offerLink": "https://s.shopee.com.br/affiliate",
                }]
            }
        }
    })
    api.session.post = Mock(return_value=response)

    first = api.get_exact_product("123", "456")
    second = api.get_exact_product("123", "456")

    assert first == second
    assert first["productCatIds"] == [1001, 1002]
    assert api.session.post.call_count == 1
    assert "productCatIds" in api.session.post.call_args.kwargs["data"].decode()
    api.close()


def test_generated_short_link_is_cached_for_same_canonical_url():
    api = ShopeeAffiliateAPI(app_id="app", secret_key="secret")
    api._post = Mock(return_value={
        "data": {"generateShortLink": {"shortLink": "https://s.shopee.com.br/short"}}
    })

    first = api.generate_short_link("https://shopee.com.br/product/123/456")
    second = api.generate_short_link("https://shopee.com.br/product/123/456")

    assert first == second == {"short_link": "https://s.shopee.com.br/short"}
    assert api._post.call_count == 1
    api.close()



def test_short_link_resolver_retries_transient_tls_error(monkeypatch):
    import requests

    from ArmoredVision.modules.v1.shopee_resolver import resolve_short_url

    monkeypatch.setenv("SHOPEE_RESOLVE_MAX_RETRIES", "2")
    monkeypatch.setenv("SHOPEE_RESOLVE_RETRY_BASE_SECONDS", "0")
    response = Mock()
    response.url = "https://shopee.com.br/product/123/456"
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.close.return_value = None
    client = Mock()
    client.get.side_effect = [
        requests.exceptions.SSLError("unexpected EOF during TLS handshake"),
        response,
    ]

    resolved = resolve_short_url("https://s.shopee.com.br/short", session=client)

    assert (resolved.shop_id, resolved.item_id) == ("123", "456")
    assert client.get.call_count == 2
    response.close.assert_called_once()
