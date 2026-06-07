import unittest


class RedactOutputValueTestCase(unittest.TestCase):
    def test_redacts_token_in_url(self):
        from desktop_py.core.fetcher_output import _redact_output_value
        result = _redact_output_value("https://example.com?token=abc123&other=1")
        self.assertNotIn("abc123", result)
        self.assertIn("token=***", result)

    def test_redacts_token_in_dict(self):
        from desktop_py.core.fetcher_output import _redact_output_value
        result = _redact_output_value({"token": "secret123", "name": "test"})
        self.assertEqual(result["token"], "***")
        self.assertEqual(result["name"], "test")

    def test_redacts_token_in_nested_list(self):
        from desktop_py.core.fetcher_output import _redact_output_value
        result = _redact_output_value([{"token": "secret"}])
        self.assertEqual(result[0]["token"], "***")

    def test_redacts_token_in_nested_dict(self):
        from desktop_py.core.fetcher_output import _redact_output_value
        result = _redact_output_value({"data": {"token": "secret", "id": 1}})
        self.assertEqual(result["data"]["token"], "***")
        self.assertEqual(result["data"]["id"], 1)

    def test_handles_non_dict_non_list(self):
        from desktop_py.core.fetcher_output import _redact_output_value
        self.assertEqual(_redact_output_value("plain"), "plain")
        self.assertEqual(_redact_output_value(42), 42)
        self.assertIsNone(_redact_output_value(None))
