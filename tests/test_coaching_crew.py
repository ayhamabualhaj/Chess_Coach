import unittest

from ai.flows.coaching_flow import CoachingError, run_coaching
from ai.tools.crew_tools import CoachData, make_tools
from ai.tools.stats_tools import MoveRecord
from tests.fake_llm import FakeLLM, final_answer, use_tool, weakness

AFTER_D5 = "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
RECORDS = [
    MoveRecord(game_id=7, ply=1, san="e4", fen_before="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
               phase="opening", cp_loss=0, best_move_uci="e2e4", label="best"),
    MoveRecord(game_id=7, ply=3, san="Qg4", fen_before=AFTER_D5, phase="opening", cp_loss=940,
               severity="blunder", motif="hanging_piece", best_move_uci="e4d5", label="blunder"),
]


def run(*replies, records=RECORDS, player=None):
    llm = FakeLLM(model="fake/coach", replies=list(replies))
    return run_coaching(records, llm, player=player), llm


class CoachingFlowTests(unittest.TestCase):
    def test_tools_then_answer(self):
        result, llm = run(
            use_tool("get_mistake_summary"), use_tool("get_worst_moves", limit=3), final_answer(weakness(7))
        )
        self.assertEqual(result.summary, "You leave your queen where it can be taken.")
        self.assertEqual(result.weaknesses[0]["example_game_ids"], [7])
        self.assertEqual([c.name for c in result.tool_calls], ["get_mistake_summary", "get_worst_moves"])
        self.assertEqual((result.turns, result.input_tokens, result.output_tokens), (3, 300, 60))
        self.assertEqual(result.model, "fake/coach")
        self.assertIn('"best_move": "exd5"', str(llm.prompts[-1]))

    def test_prompts_come_from_the_yaml_files(self):
        _, llm = run(final_answer(weakness(7)), player={"name": "ayham", "rating": 1200})
        prompt = str(llm.prompts[0])
        self.assertIn("You are Chess coach", prompt)
        self.assertIn("Player: ayham", prompt)
        self.assertIn("Rating: 1200", prompt)
        self.assertIn("Analysed: 1 games, 2 of their moves.", prompt)

    def test_practice_list_is_built_from_the_mistakes(self):
        result, _ = run(final_answer(weakness(7)))
        self.assertEqual((result.practice[0]["theme"], result.practice[0]["puzzles"]), ("hangingPiece", 3))

    def test_invented_game_is_rejected_and_the_agent_fixes_it(self):
        result, llm = run(final_answer(weakness(99)), final_answer(weakness(7)))
        self.assertEqual(result.weaknesses[0]["example_game_ids"], [7])
        self.assertIn("cites games that are not in the data: [99]", str(llm.prompts[-1]))

    def test_answer_that_stays_wrong_fails(self):
        with self.assertRaises(CoachingError):
            run(final_answer(weakness(99)), final_answer(weakness(99)), final_answer(weakness(99)))

    def test_weaknesses_are_sorted_by_priority(self):
        result, _ = run(final_answer(weakness(7, "Second", priority=2), weakness(7, "First", priority=1)))
        self.assertEqual([w["title"] for w in result.weaknesses], ["First", "Second"])

    def test_bad_tool_input_goes_back_to_the_agent(self):
        result, llm = run(use_tool("explain_position", fen_before="bad", played_move="e4", best_move="e5"),
                          final_answer(weakness(7)))
        self.assertTrue(result.tool_calls[0].is_error)
        self.assertIn("Invalid position or move", str(llm.prompts[-1]))

    def test_ai_error_becomes_a_coaching_error(self):
        with self.assertRaisesRegex(CoachingError, "could not finish the report"):
            run(RuntimeError("overloaded"))

    def test_no_moves_does_not_call_the_model(self):
        llm = FakeLLM(model="fake/coach", replies=[])
        with self.assertRaisesRegex(CoachingError, "No analysed moves"):
            run_coaching([], llm)
        self.assertEqual(llm.prompts, [])


class CrewToolTests(unittest.TestCase):
    def setUp(self):
        self.data = CoachData(RECORDS)
        self.tools = {tool.name: tool for tool in make_tools(self.data)}

    def test_explain_position_takes_normal_notation(self):
        result = self.tools["explain_position"].run(fen_before=AFTER_D5, played_move="Qg4", best_move="exd5")
        self.assertIn("hanging_piece", result)

    def test_invalid_arguments_are_rejected_before_the_tool_runs(self):
        with self.assertRaises(ValueError):
            self.tools["get_worst_moves"].run(limit=20)
        with self.assertRaises(ValueError):
            self.tools["get_worst_moves"].run(motif="nonsense")
        self.assertEqual(self.data.calls, [])

    def test_every_call_is_logged(self):
        self.tools["get_mistake_summary"].run()
        self.tools["get_opening_breakdown"].run(min_games=1)
        self.assertEqual([c.name for c in self.data.calls], ["get_mistake_summary", "get_opening_breakdown"])