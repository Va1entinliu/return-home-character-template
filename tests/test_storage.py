import tempfile
import unittest
from pathlib import Path

from app.storage import ConversationStore, RequestConflict


class StorageTests(unittest.TestCase):
    def test_chat_is_idempotent_and_survives_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conversation.sqlite3"
            store = ConversationStore(path)
            state = store.begin_chat("session-one", "request-one", "你好")
            self.assertEqual(state["status"], "pending")
            self.assertEqual(len(store.messages("session-one")), 1)

            store.complete_chat(
                "session-one",
                "request-one",
                "你好",
                "欢迎回来",
            )
            reopened = ConversationStore(path)
            state = reopened.begin_chat("session-one", "request-one", "你好")
            self.assertEqual(state["status"], "completed")
            self.assertEqual(state["response_text"], "欢迎回来")
            self.assertEqual(len(reopened.messages("session-one")), 2)

    def test_request_id_cannot_be_reused_with_different_text(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationStore(Path(directory) / "conversation.sqlite3")
            store.begin_chat("session-one", "request-one", "第一条")
            with self.assertRaises(RequestConflict):
                store.begin_chat("session-one", "request-one", "不同文本")

    def test_sessions_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationStore(Path(directory) / "conversation.sqlite3")
            store.begin_chat("session-one", "request-one", "会话一")
            store.begin_chat("session-two", "request-one", "会话二")
            self.assertEqual(
                store.messages("session-one")[0]["content"],
                "会话一",
            )
            self.assertEqual(
                store.messages("session-two")[0]["content"],
                "会话二",
            )


if __name__ == "__main__":
    unittest.main()

