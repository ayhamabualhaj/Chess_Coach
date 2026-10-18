from typing import Any

from crewai import Agent, Crew, Process, Task, TaskOutput
from crewai.project import CrewBase, agent, crew, task
from pydantic import ValidationError

from ai.tools.crew_tools import CoachData, make_tools

from .schemas import Diagnosis

MAX_ITER = 8
GUARDRAIL_RETRIES = 2


def parse_diagnosis(output: TaskOutput) -> Diagnosis:
    if isinstance(output.pydantic, Diagnosis):
        return output.pydantic
    text = output.raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    return Diagnosis.model_validate_json(text)


@CrewBase
class DiagnosisCrew:
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, data: CoachData, llm, verbose: bool = False):
        self.data = data
        self.llm = llm
        self.verbose = verbose

    def check_diagnosis(self, output: TaskOutput) -> tuple[bool, Any]:
        try:
            diagnosis = parse_diagnosis(output)
        except ValidationError as exc:
            return self.reject(f"The answer does not match the required structure: {exc}")
        for weakness in diagnosis.weaknesses:
            unknown = set(weakness.example_game_ids) - self.data.game_ids
            if unknown:
                return self.reject(
                    f"Weakness '{weakness.title}' cites games that are not in the data: "
                    f"{sorted(unknown)}. Only use game ids returned by the tools."
                )
        output.pydantic = diagnosis
        return True, output

    def reject(self, reason: str) -> tuple[bool, str]:
        self.data.rejections.append(reason)
        return False, reason

    @agent
    def chess_coach(self) -> Agent:
        return Agent(
            config=self.agents_config["chess_coach"],
            llm=self.llm,
            tools=make_tools(self.data),
            max_iter=MAX_ITER,
            allow_delegation=False,
            verbose=self.verbose,
        )

    @task
    def diagnose_task(self) -> Task:
        return Task(
            config=self.tasks_config["diagnose_task"],
            output_pydantic=Diagnosis,
            guardrail=self.check_diagnosis,
            guardrail_max_retries=GUARDRAIL_RETRIES,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=self.verbose,
        )