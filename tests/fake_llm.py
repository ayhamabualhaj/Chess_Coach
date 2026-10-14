import json

from crewai.llms.base_llm import BaseLLM


class FakeLLM(BaseLLM):
    replies: list = []
    prompts: list = []

    def call(self, messages, tools=None, callbacks=None, available_functions=None,
             from_task=None, from_agent=None, response_model=None):
        self.prompts.append(messages)
        self._track_token_usage_internal({"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def supports_function_calling(self) -> bool:
        return False


def use_tool(name: str, **args) -> str:
    return f"Thought: I need more data\nAction: {name}\nAction Input: {json.dumps(args)}"


def weakness(game_id: int, title: str = "Hanging pieces", priority: int = 1) -> dict:
    return {
        "title": title, "category": "tactics",
        "explanation": "Pieces are left undefended.", "evidence": "2. Qg4 lost the queen.",
        "example_game_ids": [game_id], "priority": priority,
        "how_to_improve": "Check every attacked piece before you move.",
        "exercises": ["10 hanging-piece puzzles a day"],
    }


def final_answer(*weaknesses: dict) -> str:
    diagnosis = {"summary": "You leave your queen where it can be taken.", "weaknesses": list(weaknesses)}
    return "Thought: I can answer now\nFinal Answer: " + json.dumps(diagnosis)