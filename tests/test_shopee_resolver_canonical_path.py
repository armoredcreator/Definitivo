from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from ArmoredVision.modules.v1.shopee_resolver import _extract, resolve_short_url


class ShopeeCanonicalProductUrlTests(unittest.TestCase):
    def test_extracts_ids_from_canonical_product_slug(self):
        url = (
            "https://shopee.com.br/"
            "Cute-Comfy-Coloring-Book-for-Adults-i.482840775.20497996294"
            "?sp_atk=example"
        )
        self.assertEqual(_extract(url), ("482840775", "20497996294"))

    def test_resolves_short_url_redirecting_to_canonical_product_slug(self):
        short_url = "https://s.shopee.com.br/example"
        canonical_url = (
            "https://shopee.com.br/"
            "Cute-Comfy-Coloring-Book-for-Adults-i.482840775.20497996294"
            "?sp_atk=example"
        )
        response = Mock()
        response.url = canonical_url
        response.status_code = 200
        with patch(
            "ArmoredVision.modules.v1.shopee_resolver.requests.get",
            return_value=response,
        ) as get:
            result = resolve_short_url(short_url)
        self.assertEqual((result.shop_id, result.item_id), ("482840775", "20497996294"))
        self.assertEqual(result.original_url, short_url)
        self.assertEqual(result.resolved_url, canonical_url)
        response.raise_for_status.assert_called_once()
        response.close.assert_called_once()
        get.assert_called_once()

    def test_does_not_treat_store_url_as_product(self):
        self.assertIsNone(_extract("https://shopee.com.br/saleritas"))


if __name__ == "__main__":
    unittest.main()
