import unittest

from app.memory import (
    INDEX_VERSION,
    LocalHistoryIndex,
    recent_complete_turns,
)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.messages = [
            {"id": "u1", "role": "user", "content": "明天去上海图书馆靠窗位置"},
            {"id": "a1", "role": "assistant", "content": "我会提前留座"},
        ]
        for index in range(12):
            self.messages.extend(
                [
                    {
                        "id": f"u{index + 2}",
                        "role": "user",
                        "content": f"普通话题 {index}",
                    },
                    {
                        "id": f"a{index + 2}",
                        "role": "assistant",
                        "content": f"普通回复 {index}",
                    },
                ]
            )

    def test_retrieves_old_complete_turn(self):
        index = LocalHistoryIndex(self.messages)
        recent = recent_complete_turns(self.messages, max_turns=10)
        recent_ids = {item["id"] for item in recent}
        result = index.retrieve(
            "还记得上海图书馆靠窗的位置吗",
            exclude_message_ids=recent_ids,
        )
        self.assertEqual([item["id"] for item in result[0]], ["u1", "a1"])

    def test_recent_keeps_complete_turns(self):
        recent = recent_complete_turns(self.messages, max_turns=4)
        self.assertEqual(len(recent), 8)
        self.assertEqual(recent[0]["role"], "user")
        self.assertEqual(recent[1]["role"], "assistant")

    def test_ordinary_chat_skips_old_history_retrieval(self):
        selection = LocalHistoryIndex(self.messages).select_context("Good night.")
        self.assertFalse(selection.stats["recallTriggered"])
        self.assertEqual(
            selection.stats["retrievalSkippedReason"],
            "no_recall_intent",
        )
        self.assertEqual(selection.retrieved_turns, ())

    def test_future_reminder_is_not_historical_recall(self):
        selection = LocalHistoryIndex(self.messages).select_context(
            "记得明天提醒我带伞。"
        )
        self.assertFalse(selection.stats["recallTriggered"])
        self.assertEqual(
            selection.stats["retrievalSkippedReason"],
            "future_reminder",
        )

    def test_recent_policy_keeps_four_to_twelve_complete_turns(self):
        index = LocalHistoryIndex(self.messages)
        roomy = index.select_context("普通聊天", recent_token_budget=10000)
        self.assertEqual(roomy.stats["recentTurnCount"], 12)
        self.assertEqual(len(roomy.recent_messages), 24)

        tight = index.select_context("普通聊天", recent_token_budget=1)
        self.assertEqual(tight.stats["recentTurnCount"], 4)
        self.assertEqual(len(tight.recent_messages), 8)

    def test_oversized_retrieval_is_skipped_without_truncating_source(self):
        messages = [
            {
                "id": "old-u",
                "role": "user",
                "content": "上海图书馆" + "很长的原文" * 200,
            },
            {
                "id": "old-a",
                "role": "assistant",
                "content": "对应回复",
            },
            *self.messages[2:],
        ]
        selection = LocalHistoryIndex(messages).select_context(
            "你还记得上海图书馆吗？",
            retrieval_token_budget=30,
        )
        self.assertEqual(selection.retrieved_turns, ())
        self.assertEqual(selection.stats["estimatedRetrievedTokens"], 0)

    def test_index_metadata_has_version_and_source_tail(self):
        metadata = LocalHistoryIndex(self.messages).index_metadata()
        self.assertEqual(metadata["version"], INDEX_VERSION)
        self.assertEqual(metadata["messageCount"], len(self.messages))
        self.assertEqual(metadata["lastMessageId"], self.messages[-1]["id"])


if __name__ == "__main__":
    unittest.main()
