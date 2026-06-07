import json
import unittest
from pathlib import Path
from unittest.mock import patch


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


class WriteFetchArtifactsTestCase(unittest.TestCase):
    """Tests for write_fetch_artifacts that verify file writing and redaction."""

    @patch("desktop_py.core.fetcher_output.write_account_output_json")
    @patch("desktop_py.core.fetcher_output.write_account_output_text")
    def test_writes_page_html(self, mock_text, mock_json):
        from desktop_py.core.fetcher_output import write_fetch_artifacts

        write_fetch_artifacts(
            account_name="test_account",
            page_html="<html>test</html>",
        )
        mock_text.assert_called_once_with("test_account", "page.html", "<html>test</html>")
        mock_json.assert_not_called()

    @patch("desktop_py.core.fetcher_output.write_account_output_json")
    @patch("desktop_py.core.fetcher_output.write_account_output_text")
    def test_writes_frame_html(self, mock_text, mock_json):
        from desktop_py.core.fetcher_output import write_fetch_artifacts

        write_fetch_artifacts(
            account_name="test_account",
            frame_html="<html>frame</html>",
        )
        mock_text.assert_called_once_with("test_account", "iframe.html", "<html>frame</html>")

    @patch("desktop_py.core.fetcher_output.write_account_output_json")
    @patch("desktop_py.core.fetcher_output.write_account_output_text")
    def test_writes_frame_text(self, mock_text, mock_json):
        from desktop_py.core.fetcher_output import write_fetch_artifacts

        write_fetch_artifacts(
            account_name="test_account",
            frame_text="some text content",
        )
        mock_text.assert_called_once_with("test_account", "iframe.txt", "some text content")

    @patch("desktop_py.core.fetcher_output.write_account_output_json")
    @patch("desktop_py.core.fetcher_output.write_account_output_text")
    def test_writes_all_artifacts(self, mock_text, mock_json):
        from desktop_py.core.fetcher_output import write_fetch_artifacts

        write_fetch_artifacts(
            account_name="acct",
            page_html="<html>page</html>",
            frame_html="<html>frame</html>",
            frame_text="frame text",
            captures=[{"url": "https://example.com", "body": "data"}],
        )
        self.assertEqual(mock_text.call_count, 3)
        mock_json.assert_called_once()
        json_args = mock_json.call_args[0]
        self.assertEqual(json_args[0], "acct")
        self.assertEqual(json_args[1], "responses.json")

    @patch("desktop_py.core.fetcher_output.write_account_output_json")
    @patch("desktop_py.core.fetcher_output.write_account_output_text")
    def test_redacts_tokens_in_captures(self, mock_text, mock_json):
        from desktop_py.core.fetcher_output import write_fetch_artifacts

        captures = [{"url": "https://api.com?token=secret123&other=1", "body": "ok"}]
        write_fetch_artifacts(
            account_name="test_account",
            captures=captures,
        )
        # Verify the redacted payload passed to write_account_output_json
        redacted = mock_json.call_args[0][2]
        self.assertNotIn("secret123", json.dumps(redacted))
        self.assertIn("token=***", redacted[0]["url"])

    @patch("desktop_py.core.fetcher_output.write_account_output_json")
    @patch("desktop_py.core.fetcher_output.write_account_output_text")
    def test_redacts_token_keys_in_captures(self, mock_text, mock_json):
        from desktop_py.core.fetcher_output import write_fetch_artifacts

        captures = [{"token": "my_secret_token", "name": "test"}]
        write_fetch_artifacts(
            account_name="test_account",
            captures=captures,
        )
        redacted = mock_json.call_args[0][2]
        self.assertEqual(redacted[0]["token"], "***")
        self.assertEqual(redacted[0]["name"], "test")

    @patch("desktop_py.core.fetcher_output.write_account_output_json")
    @patch("desktop_py.core.fetcher_output.write_account_output_text")
    def test_skips_empty_page_html(self, mock_text, mock_json):
        from desktop_py.core.fetcher_output import write_fetch_artifacts

        write_fetch_artifacts(
            account_name="test_account",
            page_html="",
        )
        mock_text.assert_not_called()

    @patch("desktop_py.core.fetcher_output.write_account_output_json")
    @patch("desktop_py.core.fetcher_output.write_account_output_text")
    def test_skips_none_captures(self, mock_text, mock_json):
        from desktop_py.core.fetcher_output import write_fetch_artifacts

        write_fetch_artifacts(
            account_name="test_account",
            captures=None,
        )
        mock_json.assert_not_called()

    @patch("desktop_py.core.fetcher_output.write_account_output_json")
    @patch("desktop_py.core.fetcher_output.write_account_output_text")
    def test_skips_empty_captures_list(self, mock_text, mock_json):
        from desktop_py.core.fetcher_output import write_fetch_artifacts

        write_fetch_artifacts(
            account_name="test_account",
            captures=[],
        )
        # Empty list is falsy, should be skipped
        mock_json.assert_not_called()

    @patch("desktop_py.core.fetcher_output.write_account_output_json")
    @patch("desktop_py.core.fetcher_output.write_account_output_text")
    def test_skips_empty_frame_html_and_text(self, mock_text, mock_json):
        from desktop_py.core.fetcher_output import write_fetch_artifacts

        write_fetch_artifacts(
            account_name="test_account",
            frame_html="",
            frame_text="",
        )
        mock_text.assert_not_called()

    @patch("desktop_py.core.fetcher_output.write_account_output_json")
    @patch("desktop_py.core.fetcher_output.write_account_output_text")
    def test_no_artifacts_written_with_all_defaults(self, mock_text, mock_json):
        from desktop_py.core.fetcher_output import write_fetch_artifacts

        write_fetch_artifacts(account_name="test_account")
        mock_text.assert_not_called()
        mock_json.assert_not_called()

    @patch("desktop_py.core.fetcher_output.write_account_output_json")
    @patch("desktop_py.core.fetcher_output.write_account_output_text")
    def test_redacts_nested_token_in_captures(self, mock_text, mock_json):
        from desktop_py.core.fetcher_output import write_fetch_artifacts

        captures = [
            {
                "headers": {"Authorization": "Bearer xyz"},
                "data": {"token": "deep_secret", "id": 42},
                "url": "https://api.com?token=url_secret&key=abc",
            }
        ]
        write_fetch_artifacts(
            account_name="test_account",
            captures=captures,
        )
        redacted = mock_json.call_args[0][2]
        serialized = json.dumps(redacted)
        self.assertNotIn("deep_secret", serialized)
        self.assertNotIn("url_secret", serialized)
        self.assertEqual(redacted[0]["data"]["token"], "***")
        self.assertIn("token=***", redacted[0]["url"])
        self.assertEqual(redacted[0]["data"]["id"], 42)
