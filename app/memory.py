from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable


RECENT_TOKEN_BUDGET = 1600
RETRIEVAL_TOKEN_BUDGET = 500
MIN_RECENT_TURNS = 4
MAX_RECENT_TURNS = 12
MAX_RETRIEVED_SNIPPETS = 2
MIN_RETRIEVAL_SCORE = 3.0
INDEX_VERSION = 2

LATIN_WORD = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*")
CHINESE_RUN = re.compile(r"[\u3400-\u9fff]+")
ENGLISH_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can",
    "could", "did", "do", "does", "for", "from", "had", "has", "have", "he",
    "her", "him", "his", "how", "i", "if", "in", "is", "it", "its", "me",
    "my", "of", "on", "or", "our", "she", "so", "that", "the", "their",
    "them", "then", "there", "they", "this", "to", "us", "was", "we",
    "were", "what", "when", "where", "which", "who", "why", "will", "with",
    "would", "you", "your",
}
CHINESE_STOP_TERMS = {
    "一个", "一下", "不是", "为什么", "什么", "他们", "你们", "你知道",
    "你还", "可以", "可能", "告诉", "因为", "已经", "应该", "怎么",
    "怎么样", "我们", "是不是", "时候", "有点", "现在", "知道", "这个",
    "这里", "那个", "还是", "就是", "然后", "的话", "真的", "记得",
    "说过", "过去", "以前", "事情", "东西", "需要", "还有", "这样",
}
RECALL_NOISE = {
    "again", "before", "ever", "last", "recall", "remember", "time",
    "记得", "想起", "回忆", "上次", "以前", "那次", "曾经", "来着",
}
STRONG_RECALL_PATTERNS = (
    re.compile(r"\b(?:do|did|can|could)\s+you\s+(?:still\s+)?(?:remember|recall)\b", re.I),
    re.compile(r"\bremember\s+when\b", re.I),
    re.compile(r"\bwhat\s+happened\s+(?:the\s+)?last\s+time\b", re.I),
    re.compile(r"你还?记得.{0,24}(?:吗|么|不)"),
    re.compile(r"记不记得"),
    re.compile(r"还记得以前"),
    re.compile(r"上次我们"),
)
FUTURE_REMINDER_PATTERNS = (
    re.compile(r"\bremember\s+to\s+\w+", re.I),
    re.compile(r"\bdon['’]?t\s+forget\s+to\s+\w+", re.I),
    re.compile(r"记得.{0,8}(?:明天|稍后|等会|待会|提醒|要做|别忘)"),
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def normalize_candidate(text: str) -> str:
    return normalize_text(text).strip(
        " \t\r\n.,!?;:，。！？；：“”‘’\"'（）()【】[]{}…—-"
    )


def _is_chinese(term: str) -> bool:
    return bool(term) and CHINESE_RUN.fullmatch(term) is not None


def search_terms(text: str) -> set[str]:
    normalized = normalize_text(text)
    terms = {
        word
        for word in LATIN_WORD.findall(normalized)
        if len(word) >= 2 and word not in ENGLISH_STOP_WORDS
    }
    for run in CHINESE_RUN.findall(normalized):
        if 2 <= len(run) <= 8 and run not in CHINESE_STOP_TERMS:
            terms.add(run)
        for size in (4, 3, 2):
            for start in range(max(0, len(run) - size + 1)):
                term = run[start : start + size]
                if term not in CHINESE_STOP_TERMS:
                    terms.add(term)
    return terms


def meaningful_terms(text: str) -> set[str]:
    return {
        term
        for term in search_terms(text)
        if term not in RECALL_NOISE
        and not any(
            _is_chinese(term) and noise in term
            for noise in RECALL_NOISE
            if _is_chinese(noise)
        )
    }


def estimate_text_tokens(text: str) -> int:
    value = str(text or "")
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", value))
    latin_words = LATIN_WORD.findall(value)
    latin_characters = sum(len(word) for word in latin_words)
    remaining = max(0, len(value) - cjk_count - latin_characters)
    return max(1, math.ceil(cjk_count * 1.05 + len(latin_words) * 1.3 + remaining / 4))


def estimate_message_tokens(message: dict) -> int:
    return 4 + estimate_text_tokens(str(message.get("content") or ""))


@dataclass(frozen=True)
class Turn:
    index: int
    messages: tuple[dict, ...]
    terms: frozenset[str]
    normalized_body: str
    normalized_messages: tuple[str, ...]

    @property
    def message_ids(self) -> set[str]:
        return {str(message.get("id", "")) for message in self.messages}

    @property
    def token_cost(self) -> int:
        return sum(estimate_message_tokens(message) for message in self.messages)


@dataclass(frozen=True)
class RecallDecision:
    triggered: bool
    score: int
    signals: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ContextSelection:
    recent_messages: tuple[dict, ...]
    retrieved_turns: tuple[tuple[dict, ...], ...]
    stats: dict


class LocalHistoryIndex:
    """A rebuildable local index. It never calls a model or edits source messages."""

    def __init__(self, messages: Iterable[dict]):
        self.turns = self._build_turns(list(messages))
        self.postings: dict[str, set[int]] = defaultdict(set)
        self.message_body_frequency: Counter[str] = Counter()
        self.turn_body_frequency: Counter[str] = Counter()
        for turn in self.turns:
            for term in turn.terms:
                self.postings[term].add(turn.index)
            self.message_body_frequency.update(
                body for body in turn.normalized_messages if body
            )
            if turn.normalized_body:
                self.turn_body_frequency[turn.normalized_body] += 1

    @staticmethod
    def _build_turns(messages: list[dict]) -> list[Turn]:
        grouped: list[list[dict]] = []
        for position, raw in enumerate(messages):
            created_at = int(raw.get("createdAt") or 0)
            message = {
                "id": str(raw.get("id") or f"local-{position}"),
                "role": "assistant" if raw.get("role") == "assistant" else "user",
                "content": str(raw.get("content") or ""),
                "createdAt": created_at,
                "timeKnown": bool(raw.get("timeKnown", created_at > 0)),
            }
            if (
                message["role"] == "assistant"
                and grouped
                and grouped[-1][0]["role"] == "user"
            ):
                grouped[-1].append(message)
            else:
                grouped.append([message])

        result = []
        for index, group in enumerate(grouped):
            normalized_messages = tuple(
                normalize_candidate(message["content"]) for message in group
            )
            normalized_body = "\n".join(
                f"{message['role']}:{body}"
                for message, body in zip(group, normalized_messages)
            )
            result.append(
                Turn(
                    index=index,
                    messages=tuple(group),
                    terms=frozenset(
                        search_terms(" ".join(message["content"] for message in group))
                    ),
                    normalized_body=normalized_body,
                    normalized_messages=normalized_messages,
                )
            )
        return result

    def index_metadata(self) -> dict:
        last_message_id = ""
        if self.turns and self.turns[-1].messages:
            last_message_id = str(self.turns[-1].messages[-1].get("id", ""))
        return {
            "version": INDEX_VERSION,
            "messageCount": sum(len(turn.messages) for turn in self.turns),
            "turnCount": len(self.turns),
            "lastMessageId": last_message_id,
        }

    def _has_rare_term(self, text: str) -> bool:
        maximum_commonness = max(2, math.ceil(max(1, len(self.turns)) * 0.02))
        return any(
            0 < len(self.postings.get(term, set())) <= maximum_commonness
            for term in meaningful_terms(text)
        )

    def analyze_recall(self, current_input: str) -> RecallDecision:
        text = normalize_text(current_input)
        if not text:
            return RecallDecision(False, 0, (), "empty_input")
        if any(pattern.search(text) for pattern in FUTURE_REMINDER_PATTERNS):
            return RecallDecision(False, 0, ("future_reminder",), "future_reminder")

        signals = []
        explicit = any(pattern.search(text) for pattern in STRONG_RECALL_PATTERNS)
        score = 4 if explicit else 0
        if explicit:
            signals.append("explicit_recall")

        tests = (
            (
                bool(re.search(r"\b(?:remember|recall)\b", text, re.I))
                or bool(re.search(r"(?:记得|想起|回忆)", text)),
                3,
                "recall_verb",
            ),
            (
                bool(re.search(r"\b(?:last\s+time|before|previously|used\s+to|back\s+then)\b", text, re.I))
                or bool(re.search(r"(?:上次|以前|那次|之前|曾经|过去)", text)),
                2,
                "past_event",
            ),
            (
                bool(re.search(r"\b(?:again|this\s+time|second\s+time)\b", text, re.I))
                or bool(re.search(r"(?:又来|再来|再次|这次|第二次)", text)),
                2,
                "again",
            ),
            (
                bool(re.search(r"\bwe\s+(?:went|met|visited|ate|saw|talked|stayed|had)\b", text, re.I))
                or bool(re.search(r"(?:我们|咱们).{0,8}(?:去过|见过|吃过|聊过|看过|住过|一起)", text)),
                2,
                "shared_action",
            ),
            (
                bool(re.search(r"\b(?:what|where|who|which)\s+(?:was|were|did)\b", text, re.I))
                or bool(re.search(r"(?:谁|哪|什么|怎么|在哪里|叫什么).{0,8}(?:来着|上次|以前|那次)", text)),
                2,
                "old_fact_question",
            ),
        )
        historical_signal = False
        recall_verb = False
        for matched, points, signal in tests:
            if matched:
                score += points
                signals.append(signal)
                if signal == "recall_verb":
                    recall_verb = True
                else:
                    historical_signal = True

        rare_term = self._has_rare_term(current_input)
        if rare_term:
            score += 1
            signals.append("rare_indexed_term")
        if re.search(r"[?？]$|(?:吗|么|来着)[?？]?$", text):
            score += 1
            signals.append("question")

        triggered = explicit or (
            score >= 3 and (historical_signal or (recall_verb and rare_term))
        )
        return RecallDecision(
            triggered,
            score,
            tuple(dict.fromkeys(signals)),
            "" if triggered else "no_recall_intent",
        )

    @staticmethod
    def _flatten(turns: list[Turn]) -> tuple[dict, ...]:
        return tuple(dict(message) for turn in turns for message in turn.messages)

    @staticmethod
    def _comparison_terms(text: str) -> set[str]:
        normalized = normalize_candidate(text)
        terms = set(LATIN_WORD.findall(normalized))
        chinese = "".join(CHINESE_RUN.findall(normalized))
        for size in (3, 2):
            terms.update(
                chinese[start : start + size]
                for start in range(max(0, len(chinese) - size + 1))
            )
        return terms

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0
        return len(left & right) / len(left | right)

    def select_context(
        self,
        current_input: str,
        *,
        recent_token_budget: int = RECENT_TOKEN_BUDGET,
        retrieval_token_budget: int = RETRIEVAL_TOKEN_BUDGET,
        min_recent_turns: int = MIN_RECENT_TURNS,
        max_recent_turns: int = MAX_RECENT_TURNS,
        max_snippets: int = MAX_RETRIEVED_SNIPPETS,
    ) -> ContextSelection:
        recent_turns: list[Turn] = []
        recent_tokens = 0
        for turn in reversed(self.turns):
            if len(recent_turns) >= max_recent_turns:
                break
            if (
                len(recent_turns) >= min_recent_turns
                and recent_tokens + turn.token_cost > recent_token_budget
            ):
                break
            recent_turns.insert(0, turn)
            recent_tokens += turn.token_cost

        recent_ids = {
            message_id for turn in recent_turns for message_id in turn.message_ids
        }
        decision = self.analyze_recall(current_input)
        common_stats = {
            "recentTurnCount": len(recent_turns),
            "recentMessageCount": sum(len(turn.messages) for turn in recent_turns),
            "estimatedRecentTokens": recent_tokens,
            "recallTriggered": decision.triggered,
            "recallScore": decision.score,
            "recallSignals": list(decision.signals),
        }
        if not decision.triggered:
            return ContextSelection(
                self._flatten(recent_turns),
                (),
                {
                    **common_stats,
                    "retrievalSkippedReason": decision.reason,
                    "retrievalCandidateCount": 0,
                    "duplicateSuppressedCount": 0,
                    "retrievedSnippetCount": 0,
                    "retrievedMessageCount": 0,
                    "estimatedRetrievedTokens": 0,
                },
            )

        recent_user_messages = [
            message
            for turn in self.turns
            for message in turn.messages
            if message["role"] == "user"
        ][-2:]
        term_weights = {term: 1.0 for term in meaningful_terms(current_input)}
        for offset, message in enumerate(reversed(recent_user_messages)):
            weight = 0.35 if offset == 0 else 0.20
            for term in meaningful_terms(message["content"]):
                if term in self.postings:
                    term_weights[term] = max(term_weights.get(term, 0), weight)

        query_terms = {
            term
            for term in term_weights
            if any(
                not (self.turns[index].message_ids & recent_ids)
                for index in self.postings.get(term, set())
            )
        }
        if not query_terms:
            return ContextSelection(
                self._flatten(recent_turns),
                (),
                {
                    **common_stats,
                    "retrievalSkippedReason": "no_searchable_entity",
                    "retrievalCandidateCount": 0,
                    "duplicateSuppressedCount": 0,
                    "retrievedSnippetCount": 0,
                    "retrievedMessageCount": 0,
                    "estimatedRetrievedTokens": 0,
                },
            )

        scores: dict[int, float] = defaultdict(float)
        matches: dict[int, set[str]] = defaultdict(set)
        for term in query_terms:
            posting = self.postings.get(term, set())
            inverse_frequency = math.log((len(self.turns) + 1) / (len(posting) + 1)) + 1
            term_weight = 1 + min(3, max(0, len(term) - 1)) * 0.45
            for turn_index in posting:
                turn = self.turns[turn_index]
                if turn.message_ids & recent_ids:
                    continue
                scores[turn_index] += (
                    inverse_frequency * term_weight * term_weights.get(term, 1)
                )
                matches[turn_index].add(term)

        candidates = []
        for turn_index, raw_score in scores.items():
            turn = self.turns[turn_index]
            frequency_penalty = (
                math.log2(self.turn_body_frequency[turn.normalized_body]) * 1.4
                + math.log2(
                    max(
                        1,
                        *(
                            self.message_body_frequency[body]
                            for body in turn.normalized_messages
                            if body
                        ),
                    )
                )
                * (1.6 if len(turn.normalized_body) < 48 else 0.7)
            )
            coverage = len(matches[turn_index]) / max(1, len(query_terms))
            score = raw_score + coverage * 2 - frequency_penalty
            strong_match = any(
                len(term) >= (3 if _is_chinese(term) else 5)
                for term in matches[turn_index]
            )
            if score >= MIN_RETRIEVAL_SCORE and (
                strong_match or len(matches[turn_index]) >= min(2, len(query_terms))
            ):
                candidates.append((score, turn, matches[turn_index]))
        candidates.sort(key=lambda item: (-item[0], -item[1].index))

        selected: list[Turn] = []
        selected_matches: set[str] = set()
        selected_bodies: set[str] = set()
        retrieval_tokens = 0
        duplicate_count = 0
        for score, turn, turn_matches in candidates:
            if len(selected) >= max_snippets:
                break
            if turn.normalized_body in selected_bodies:
                duplicate_count += 1
                continue
            if len(turn.normalized_body) >= 24 and any(
                len(other.normalized_body) >= 24
                and self._jaccard(
                    self._comparison_terms(turn.normalized_body),
                    self._comparison_terms(other.normalized_body),
                )
                > 0.85
                for other in selected
            ):
                duplicate_count += 1
                continue
            if selected and not (turn_matches - selected_matches):
                continue
            if turn.token_cost > retrieval_token_budget:
                continue
            if retrieval_tokens + turn.token_cost > retrieval_token_budget:
                continue
            selected.append(turn)
            selected_bodies.add(turn.normalized_body)
            selected_matches.update(turn_matches)
            retrieval_tokens += turn.token_cost

        selected.sort(key=lambda turn: turn.index)
        retrieved = tuple(
            tuple(dict(message) for message in turn.messages) for turn in selected
        )
        return ContextSelection(
            self._flatten(recent_turns),
            retrieved,
            {
                **common_stats,
                "retrievalSkippedReason": (
                    "" if retrieved else "below_relevance_threshold"
                ),
                "retrievalCandidateCount": len(candidates),
                "duplicateSuppressedCount": duplicate_count,
                "retrievedSnippetCount": len(retrieved),
                "retrievedMessageCount": sum(len(turn) for turn in retrieved),
                "estimatedRetrievedTokens": retrieval_tokens,
            },
        )

    def retrieve(
        self,
        query: str,
        *,
        max_snippets: int = MAX_RETRIEVED_SNIPPETS,
        exclude_message_ids: set[str] | None = None,
    ) -> list[list[dict]]:
        """Compatibility helper. New code should use select_context()."""
        selection = self.select_context(query, max_snippets=max_snippets)
        excluded = exclude_message_ids or set()
        return [
            [dict(message) for message in turn]
            for turn in selection.retrieved_turns
            if not {str(message.get("id", "")) for message in turn} & excluded
        ]


def recent_complete_turns(messages: list[dict], max_turns: int = 10) -> list[dict]:
    turns = LocalHistoryIndex._build_turns(messages)
    return [
        dict(message)
        for turn in turns[-max(1, max_turns) :]
        for message in turn.messages
    ]
