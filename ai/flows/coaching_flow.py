import logging
import time
from dataclasses import dataclass, field

from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel, ConfigDict

from ai.crews.diagnosis_crew import DiagnosisCrew
from ai.crews.diagnosis_crew.crew import GUARDRAIL_RETRIES
from ai.tools.crew_tools import CoachData, ToolCall
from ai.tools.practice_tools import build_practice
from ai.tools.stats_tools import MoveRecord

logger = logging.getLogger(__name__)

GENERIC_ERROR = "The AI coach could not finish the report. Please try again later."
GUARDRAIL_ERROR = "The AI coach's answer did not pass the checks, even after retries. Please try again."
PROVIDER_ERRORS = {
    "AuthenticationError": "The AI service rejected the API key. Check AI_API_KEY in .env.",
    "PermissionDeniedError": "The AI service rejected the API key. Check AI_API_KEY in .env.",
    "NotFoundError": "The AI model was not found. Check AI_MODEL in .env.",
    "RateLimitError": "The AI service is busy right now. Please try again in a few minutes.",
}


class CoachingError(Exception):
    pass


def _user_message(exc: Exception, data: CoachData) -> str:
    if len(data.rejections) > GUARDRAIL_RETRIES:
        return GUARDRAIL_ERROR
    error, depth = exc, 0
    while error is not None and depth < 10:
        if type(error).__name__ in PROVIDER_ERRORS:
            return PROVIDER_ERRORS[type(error).__name__]
        error, depth = error.__cause__ or error.__context__, depth + 1
    return GENERIC_ERROR


@dataclass
class CoachingResult:
    summary: str
    weaknesses: list[dict]
    model: str
    turns: int
    practice: list[dict] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0


class CoachingState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    records: list[MoveRecord] = []
    player: dict = {}


class CoachingFlow(Flow[CoachingState]):
    def __init__(self, llm, verbose: bool = False, **kwargs):
        super().__init__(suppress_flow_events=not verbose, **kwargs)
        self.llm = llm
        self.verbose = verbose

    @start()
    def check_data(self):
        if not self.state.records:
            raise CoachingError("No analysed moves yet. Analyse some games first.")

    @listen(check_data)
    def diagnose(self) -> CoachingResult:
        records = self.state.records
        data = CoachData(records)
        inputs = {
            "player_name": self.state.player.get("name") or "unknown",
            "rating": self.state.player.get("rating") or "unknown",
            "games": len(data.game_ids),
            "moves": len(records),
        }
        started = time.perf_counter()
        try:
            output = DiagnosisCrew(data, self.llm, self.verbose).crew().kickoff(inputs=inputs)
        except Exception as exc:
            logger.exception("The coaching crew failed (%d guardrail rejections)", len(data.rejections))
            raise CoachingError(_user_message(exc, data)) from exc

        diagnosis = output.pydantic
        usage = output.token_usage
        return CoachingResult(
            summary=diagnosis.summary,
            weaknesses=sorted((w.model_dump() for w in diagnosis.weaknesses), key=lambda w: w["priority"]),
            model=getattr(self.llm, "model", str(self.llm)),
            turns=usage.successful_requests,
            tool_calls=data.calls,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            seconds=time.perf_counter() - started,
        )

    @listen(diagnose)
    def build_practice_list(self, result: CoachingResult) -> CoachingResult:
        result.practice = build_practice(self.state.records)
        return result


def run_coaching(records: list[MoveRecord], llm, player: dict | None = None, verbose: bool = False) -> CoachingResult:
    flow = CoachingFlow(llm=llm, verbose=verbose)
    return flow.kickoff(inputs={"records": records, "player": player or {}})