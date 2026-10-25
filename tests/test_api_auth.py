import unittest
from unittest.mock import patch

from scripts.check_ucoin_links_api import api_request as check_ucoin_request
from scripts.sync_coin_images_api import api_request, base44_authorization


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b"[]"


class Base44AuthorizationTests(unittest.TestCase):
    def test_normalizes_a_raw_or_prefixed_token(self):
        self.assertEqual(base44_authorization(" secret "), "Bearer secret")
        self.assertEqual(base44_authorization("Bearer secret"), "Bearer secret")

    @patch("scripts.sync_coin_images_api.urlopen", return_value=FakeResponse())
    def test_shared_client_uses_authorization_bearer(self, urlopen):
        self.assertEqual(
            api_request("GET", "/entities/Coin", "secret", query={"limit": 1}),
            [],
        )

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertIsNone(request.get_header("Api_key"))

    @patch("scripts.check_ucoin_links_api.urlopen", return_value=FakeResponse())
    def test_ucoin_checker_uses_authorization_bearer(self, urlopen):
        self.assertEqual(
            check_ucoin_request("/entities/Coin", "secret", {"limit": 1}),
            [],
        )

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertIsNone(request.get_header("Api_key"))


if __name__ == "__main__":
    unittest.main()
