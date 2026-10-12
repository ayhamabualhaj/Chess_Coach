"""Tests for the diagnosis agent loop. A fake client replays scripted
responses, so no API key or network is needed."""
import json
import unittest
from types import SimpleNamespace

from ai.agents.diagnosis_agent import DiagnosisAgent, DiagnosisError
from ai.tools.stats_tools import MoveRecord

FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
# After 1. e4 d5, White to move: 2. Qg4?? hangs the queen to Bxg4.
AFTER_E4_D5 = "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"

RECORDS = [
    MoveRecord(game_id=1, ply=1, san="e4", fen_before=FEN, phase="opening", cp_loss=10),
    MoveRecord(game_id=1, ply=41, san="Qh5", fen_before=FEN, phase="middlegame", cp_loss=400,
               severity="blunder", motif="hanging_piece", best_move_uci="d2d4"),
    MoveRecord(game_id=2, ply=60, san="Rd1", fen_before=FEN, phase="endgame", cp_loss=250,
               severity="blunder", motif="hanging_piece", best_move_uci="e2e4"),
]

WEAKNESS = {
    "title": "Leaving pieces undefended",
    "category": "tactics",
    "explanation": "Pieces are left where they can be taken for free.",
    "evidence": "2 blunders with hanging_piece (400 and 250 cp).",
    "example_game_ids": [1, 2],
    "priority": 1,
    "how_to_improve": "Before every move, check which of your pieces the opponent attacks.",
    "exercises": ["Solve 10 'hanging piece' puzzles a day.", "Replay your two blunders."],
}

PLAN = {
    "overview": "One week focused on piece safety.",
    "days": 7,
    "tasks": [
        {"day": 3, "focus": "Piece safety", "activity": "Play 3 rapid games, blunder-check every move.", "minutes": 45},
        {"day": 1, "focus": "Piece safety", "activity": "Hanging-piece puzzles.", "minutes": 20},
    ],
}


def submission(weaknesses=None, plan=None, summary="Solid, but drops pieces."):
    return {"summary": summary, "weaknesses": weaknesses or [WEAKNESS], "training_plan": plan or PLAN}


def tool_use(block_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=tool_input)


def response(*content, stop_reason="tool_use"):
    usage = SimpleNamespace(input_tokens=100, output_tokens=20,
                            cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(content=list(content), stop_reason=stop_reason,
                           model="claude-opus-5-5", usage=usage)


class FakeClient:
    """Mimics client.beta.messages.create and records every request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        # Copy the message list: the agent keeps appending to it.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


def tool_results(request):
    """The tool_result blocks sent in the last user message of a request."""
    return request["messages"][-1]["content"]


class DiagnosisAgentTests(unittest.TestCase):
    def test_full_loop_uses_tools_then_submits(self):
        client = FakeClient([
            response(tool_use("t1", "get_mistake_summary", {})),
            response(tool_use("t2", "get_worst_moves", {"limit": 2, "motif": "hanging_piece", "phase": ""})),
            response(tool_use("t3", "submit_diagnosis", submission())),
        ])
        result = DiagnosisAgent(client=client).run(RECORDS, player={"name": "ayham", "rating": 1200})

        self.assertEqual(result.summary, "Solid, but drops pieces.")
        self.assertEqual(result.weaknesses[0]["title"], "Leaving pieces undefended")
        self.assertEqual(result.weaknesses[0]["exercises"][0], "Solve 10 'hanging piece' puzzles a day.")
        self.assertEqual(result.turns, 3)
        self.assertEqual([c.name for c in result.tool_calls],
                         ["get_mistake_summary", "get_worst_moves", "submit_diagnosis"])
        self.assertEqual(result.input_tokens, 300)

        # The real tool output was sent back to the model.
        summary = json.loads(tool_results(client.requests[1])[0]["content"])
        self.assertEqual(summary["by_motif"], {"hanging_piece": 2})
        worst = json.loads(tool_results(client.requests[2])[0]["content"])
        self.assertEqual([w["cp_loss"] for w in worst], [400, 250])
        self.assertIn("Rating: 1200", client.requests[0]["messages"][0]["content"])

    def test_best_move_is_given_in_normal_notation(self):
        client = FakeClient([
            response(tool_use("t1", "get_worst_moves", {"limit": 1, "motif": "", "phase": ""})),
            response(tool_use("t2", "submit_diagnosis", submission())),
        ])
        DiagnosisAgent(client=client).run(RECORDS)
        worst = json.loads(tool_results(client.requests[1])[0]["content"])
        self.assertEqual(worst[0]["best_move"], "d4")  # not "d2d4"

    def test_training_plan_is_returned_sorted_by_day(self):
        client = FakeClient([response(tool_use("t1", "submit_diagnosis", submission()))])
        result = DiagnosisAgent(client=client).run(RECORDS)
        self.assertEqual(result.training_plan["days"], 7)
        self.assertEqual([t["day"] for t in result.training_plan["tasks"]], [1, 3])

    def test_task_outside_the_plan_is_rejected_and_model_retries(self):
        bad_plan = {**PLAN, "days": 2, "tasks": [{**PLAN["tasks"][0], "day": 5}]}
        client = FakeClient([
            response(tool_use("t1", "submit_diagnosis", submission(plan=bad_plan))),
            response(tool_use("t2", "submit_diagnosis", submission())),
        ])
        result = DiagnosisAgent(client=client).run(RECORDS)
        error = tool_results(client.requests[1])[0]
        self.assertTrue(error["is_error"])
        self.assertIn("between 1 and 2", error["content"])
        self.assertEqual(result.training_plan["days"], 7)

    def test_invented_game_id_is_rejected_and_model_retries(self):
        bad = {**WEAKNESS, "example_game_ids": [99]}
        client = FakeClient([
            response(tool_use("t1", "submit_diagnosis", submission(weaknesses=[bad]))),
            response(tool_use("t2", "submit_diagnosis", submission())),
        ])
        result = DiagnosisAgent(client=client).run(RECORDS)

        error = tool_results(client.requests[1])[0]
        self.assertTrue(error["is_error"])
        self.assertIn("[99]", error["content"])
        self.assertTrue(result.tool_calls[0].is_error)
        self.assertEqual(result.weaknesses[0]["example_game_ids"], [1, 2])

    def test_parallel_tool_calls_answered_in_one_message(self):
        client = FakeClient([
            response(tool_use("a", "get_mistake_summary", {}),
                     tool_use("b", "get_opening_breakdown", {"min_games": 1})),
            response(tool_use("c", "submit_diagnosis", submission())),
        ])
        DiagnosisAgent(client=client).run(RECORDS)
        self.assertEqual([r["tool_use_id"] for r in tool_results(client.requests[1])], ["a", "b"])

    def test_explain_position_takes_normal_notation(self):
        client = FakeClient([
            response(tool_use("t1", "explain_position",
                              {"fen_before": AFTER_E4_D5, "played_move": "Qg4", "best_move": "exd5"})),
            response(tool_use("t2", "submit_diagnosis", submission())),
        ])
        DiagnosisAgent(client=client).run(RECORDS)
        result = tool_results(client.requests[1])[0]
        self.assertFalse(result["is_error"])
        self.assertEqual(json.loads(result["content"]), {"motifs": ["hanging_piece"]})

    def test_bad_position_returns_tool_error(self):
        client = FakeClient([
            response(tool_use("t1", "explain_position",
                              {"fen_before": "not a fen", "played_move": "e4", "best_move": ""})),
            response(tool_use("t2", "submit_diagnosis", submission())),
        ])
        DiagnosisAgent(client=client).run(RECORDS)
        self.assertTrue(tool_results(client.requests[1])[0]["is_error"])

    def test_text_answer_gets_one_reminder(self):
        text = SimpleNamespace(type="text", text="You hang pieces.")
        client = FakeClient([
            response(text, stop_reason="end_turn"),
            response(text, stop_reason="end_turn"),
        ])
        with self.assertRaises(DiagnosisError):
            DiagnosisAgent(client=client).run(RECORDS)
        self.assertIn("submit_diagnosis", client.requests[1]["messages"][-1]["content"])

    def test_refusal_and_turn_limit(self):
        client = FakeClient([response(stop_reason="refusal")])
        with self.assertRaises(DiagnosisError):
            DiagnosisAgent(client=client).run(RECORDS)

        looping = FakeClient([response(tool_use(str(i), "get_mistake_summary", {})) for i in range(3)])
        with self.assertRaisesRegex(DiagnosisError, "3 turns"):
            DiagnosisAgent(client=looping, max_turns=3).run(RECORDS)

    def test_no_records_does_not_call_the_api(self):
        client = FakeClient([])
        with self.assertRaises(DiagnosisError):
            DiagnosisAgent(client=client).run([])
        self.assertEqual(client.requests, [])


class FallbackParameterTests(unittest.TestCase):
    def submit_only(self):
        return FakeClient([response(tool_use("t1", "submit_diagnosis", submission()))])

    def test_haiku_requests_do_not_send_fallbacks(self):
        # Claude Haiku 5.5 has no server-side fallback.
        client = self.submit_only()
        DiagnosisAgent(client=client, model="claude-haiku-5-5").run(RECORDS)
        self.assertNotIn("fallbacks", client.requests[0])

    def test_other_models_send_default_fallbacks(self):
        client = self.submit_only()
        DiagnosisAgent(client=client, model="claude-sonnet-5-5").run(RECORDS)
        self.assertEqual(client.requests[0]["fallbacks"], "default")


if __name__ == "__main__":
    unittest.main()