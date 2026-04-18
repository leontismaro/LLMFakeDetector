import unittest

from app.modules.detection.adapter import build_chat_completions_url


class BuildChatCompletionsUrlTest(unittest.TestCase):
    def test_should_append_standard_path_when_base_url_is_root(self) -> None:
        self.assertEqual(
            build_chat_completions_url("https://example.com"),
            "https://example.com/v1/chat/completions",
        )

    def test_should_append_chat_completions_when_base_url_ends_with_v1(self) -> None:
        self.assertEqual(
            build_chat_completions_url("https://example.com/v1"),
            "https://example.com/v1/chat/completions",
        )

    def test_should_keep_full_chat_completions_endpoint(self) -> None:
        self.assertEqual(
            build_chat_completions_url("https://example.com/custom/v1/chat/completions"),
            "https://example.com/custom/v1/chat/completions",
        )

