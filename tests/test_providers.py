import unittest

from app.providers import speech_text


class ProviderTests(unittest.TestCase):
    def test_parenthetical_actions_are_not_spoken(self):
        self.assertEqual(
            speech_text("（轻轻点头）你好。(smiles) Welcome back."),
            "你好。 Welcome back.",
        )

    def test_action_only_message_has_no_speech(self):
        self.assertEqual(speech_text("（安静地抱住你）"), "")


if __name__ == "__main__":
    unittest.main()
