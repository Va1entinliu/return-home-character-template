import unittest
from pathlib import Path


class ServerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (
            Path(__file__).resolve().parents[1] / "app" / "server.py"
        ).read_text("utf-8")

    def test_every_api_route_declares_auth_dependency(self):
        for route in ("/api/health", "/api/history", "/api/chat", "/api/tts"):
            marker = f'"{route}", dependencies=[Depends(require_app_token)]'
            self.assertIn(marker, self.source)

    def test_paid_request_keys_include_session(self):
        self.assertIn(
            "key = (request.session_id, request.request_id)",
            self.source,
        )
        self.assertIn("session_locks[request.session_id]", self.source)

    def test_tts_has_single_flight_and_bounded_memory_cache(self):
        self.assertIn("tts_inflight", self.source)
        self.assertIn("tts_completed", self.source)
        self.assertIn("while len(tts_completed) > 8", self.source)

    def test_server_uses_current_context_selection_and_real_usage(self):
        self.assertIn("history_index.select_context(text)", self.source)
        self.assertIn("parse_provider_usage(character.usage)", self.source)


if __name__ == "__main__":
    unittest.main()
