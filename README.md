# Chess_Coach

**Ayham Abu-Alhaj – Final project, Data Science & AI**

A web app that turns your own chess games into personal coaching. You upload games (PGN),
the Stockfish engine analyses every move, and an AI coach (a CrewAI agent) finds your
recurring weaknesses, explains how to fix them and gives you puzzles that train exactly
the mistakes you make.

---

## 1. Problem Statement

Most club players lose games to the same few mistakes again and again: leaving pieces
undefended, missing forks, falling apart in the endgame. Chess sites show what went wrong
**in one game** ("15...Nxd7 was a blunder"), but they don't connect the dots **across many
games**, and they don't tell you *why* you keep making that mistake or *what to practise*.
A human coach does that, but a coach is expensive and not available to most players.

**Goal:** give every player a coach-like review of their own games: find the patterns behind
their mistakes, back every claim with real moves from their games, and turn it into a
concrete practice plan.

## 2. Proposed Solution

Chess_Coach combines a classical chess engine with an agentic AI layer:

1. **Upload.** Paste PGN text or upload a `.pgn` file. One file can hold any number of games
   (e.g. an export from Lichess or Chess.com). Each game is stored separately, duplicates and
   broken games are skipped, and the side you played is detected from your username.
2. **Engine analysis (Stockfish).** Every move of both sides is evaluated in the background.
   - **Mistake labels** (Inaccuracy / Mistake / Blunder) use Lichess's open-source rules
     (win-chance formula and thresholds from `lichess-org/lila`), so they can be compared with Lichess.
   - **Chess.com-style move types**: Brilliant !!, Great !, Best, Excellent, Good, Miss,
     Inaccuracy ?!, Mistake ?, Blunder ?? (based on Chess.com's published "expected points" rules).
   - **Accuracy %** per player, with Lichess's open-source formula.
   - **Tactical motifs** for each mistake (hanging piece, missed fork, allowed mate, ...),
     detected with board rules.
   - The game page shows an evaluation graph, the move table with all labels and the best move.
3. **AI coach (CrewAI agent).** You choose games; a **chess coach agent** works through your
   moves with four tools: it asks for statistics, opening results and your worst moves, re-checks
   single positions, decides itself what to look at next, and finishes with a structured report:
   2-4 recurring weaknesses, each with evidence (real moves from your games), how to improve and
   exercises. The agent cannot invent games: an answer citing an unknown game id is rejected by a
   guardrail and the agent has to correct it.
4. **Practice.** For every type of mistake you made, the report links a matching Lichess puzzle
   theme (3 puzzles per mistake), with a tick-off list and a progress bar.
5. **REST API.** Everything is also available as JSON for other programs (apps, bots, scripts),
   built with Django REST Framework serializers and token authentication.
6. **Evaluation.** A command measures the analysis against Lichess's own labels
   (precision / recall / F1) together with latency and memory per game.

**AI component — an agent, not a single API call.** The coach is built with **CrewAI**:

| Part | File | What it does |
|---|---|---|
| Flow | `ai/flows/coaching_flow.py` | `check_data` → `diagnose` → `build_practice_list`; only `diagnose` uses the AI model |
| Crew | `ai/crews/diagnosis_crew/crew.py` | one `chess_coach` agent with 4 tools, at most 8 steps (`max_iter`) |
| Prompts | `ai/crews/diagnosis_crew/config/agents.yaml`, `tasks.yaml` | who the agent is (role, goal, backstory) and what it must do — kept out of the Python code |
| Output check | `ai/crews/diagnosis_crew/schemas.py` + guardrail | the answer must match the `Diagnosis` structure and cite only games that exist; otherwise it is sent back to the agent (at most 2 retries) |
| Tools | `ai/tools/crew_tools.py` | `get_mistake_summary`, `get_opening_breakdown`, `get_worst_moves`, `explain_position` — thin wrappers around plain Python functions, so every number in a report comes from code, not from the model |

The model is chosen in `.env` (`AI_MODEL`), so the coach can run on Claude or on another
provider supported by CrewAI/LiteLLM without changing code.

**APIs used and exposed**

| Used | Purpose |
|---|---|
| Anthropic Claude API (through CrewAI; other providers possible via LiteLLM) | the AI coach |
| Stockfish via the UCI protocol (python-chess) | move evaluation |
| Lichess puzzle themes (`lichess.org/training/<theme>`) | practice links in the report |
| Lichess game export (with computer analysis) | reference labels for the evaluation |

**REST API (exposed)** – built with Django REST Framework: serializers turn models into JSON and
validate input; every endpoint needs a logged-in user (token or browser session) and only returns
the user's own data.

| Method + URL | What it does |
|---|---|
| `POST /api/token/` | send `username` + `password`, get your API token |
| `GET /api/games/?show=all` (or `todo`, `done`, `side`) | your games, 50 per page |
| `GET /api/games/<id>/` | one game with every move, its labels (Best, Blunder…) and both players' accuracy |
| `POST /api/games/<id>/analyse/` | queue the analysis (`202` queued, `409` already queued, `429` queue full) |
| `GET /api/reports/` | your coaching reports |
| `POST /api/reports/` with `{"games": [1, 2]}` | ask the AI coach for a new report (`202`) |
| `GET /api/reports/<id>/` | a full report: weaknesses, advice, practice list, tokens and time |
| `GET /games/<id>/status/`, `/games/queue/`, `/coaching/reports/<id>/status/` | status checks the pages use to refresh themselves |

Example:
```bash
curl -X POST -d "username=me&password=secret" http://127.0.0.1:8000/api/token/
curl -H "Authorization: Token <your-token>" http://127.0.0.1:8000/api/games/
```
Opened in the browser while logged in, the same URLs show Django REST Framework's browsable API.

## 3. Technologies Used

| Area | Technology |
|---|---|
| Language | Python 3.10–3.13 (CrewAI does not support 3.14 yet; developed on 3.13) |
| Web framework | Django 6.1 (server-rendered templates) |
| REST API | Django REST Framework 3.18 (serializers, token authentication) |
| Database | PostgreSQL (driver `psycopg2-binary`) |
| Background jobs | Django's built-in Tasks framework + `django-tasks-db` (worker: `python manage.py db_worker`) |
| Chess engine | Stockfish (separate program, tested with versions 16 and 18) |
| Chess logic | `chess` (python-chess): PGN parsing, board rules, UCI engine communication |
| AI agent | CrewAI 1.15 (crew, flow, tools, YAML prompts, guardrail) with LiteLLM |
| AI model | Claude Sonnet 5.5 by default (any `provider/model` in `AI_MODEL`, e.g. Claude Haiku 5.5 or Opus 5.5) |
| Front end | Bootstrap 5.3 (dark theme), Chart.js 4.4 for the evaluation graph |
| Configuration | `python-dotenv` (`.env` file) |
| Tests | Django test runner / `unittest` (209 tests) |

**Architecture.** Each request goes **View → Service → Repository / AI → Database**:
views only handle the request and response, services contain the logic, repositories are the
only code that touches the ORM, and the `ai/` package contains no Django or database code at all
(so the engine, the rules, the crew and the flow can be tested on their own). Each model has its
own file.

## 4. Project Structure

```
Chess_Coach/
├── manage.py
├── requirements.txt
├── .env.example                 # template for your .env (secrets are never committed)
├── config/                      # Django settings (incl. REST_FRAMEWORK, AI_MODEL) and root URLs
├── apps/
│   ├── accounts/                # sign-up / login, UserProfile (rating, Lichess name)
│   │   ├── models/  repositories/  services/  views/  forms.py  urls.py
│   ├── games/                   # upload, Stockfish analysis, game pages
│   │   ├── models/              # game.py, move.py, mistake.py (one model per file)
│   │   ├── repositories/        # game_repository.py, analysis_repository.py
│   │   ├── services/            # pgn_import_service, analysis_service, game_service
│   │   ├── serializers/         # game_serializers.py: models → JSON for the API
│   │   ├── views/               # game_views.py (pages), game_api_views.py (JSON API)
│   │   ├── urls.py  api_urls.py  tasks.py (background analysis)
│   │   └── management/commands/ # analyse_game, evaluate
│   └── coaching/                # weakness reports, practice list
│       ├── models/              # weakness_report.py, training_plan.py
│       ├── services/            # coaching_service, diagnosis_service (runs the AI flow)
│       ├── serializers/         # report_serializers.py
│       ├── views/               # coaching_views.py (pages), coaching_api_views.py (JSON API)
│       ├── repositories/  urls.py  api_urls.py  tasks.py
├── ai/                          # pure Python: no Django, no database
│   ├── engine/                  # stockfish_wrapper, move_classifier (Lichess rules),
│   │                            # move_types (Brilliant…Blunder), accuracy
│   ├── tools/                   # motif_tools, stats_tools, practice_tools,
│   │                            # crew_tools (the agent's 4 CrewAI tools)
│   ├── crews/diagnosis_crew/    # crew.py, schemas.py
│   │   └── config/              # agents.yaml, tasks.yaml (the prompts)
│   └── flows/coaching_flow.py   # check data → diagnose (crew) → practice list
├── evaluation/                  # performance measurement (accuracy, latency, memory)
│   ├── measure_accuracy.py  measure_latency.py  measure_memory.py  run_evaluation.py
│   └── data/games.pgn           # 10 Lichess-analysed test games
├── templates/                   # HTML (base, accounts, games, coaching)
├── static/css/style.css
├── docs/                        # evaluation results (CSV + summary) and the performance report
└── tests/                       # 209 tests (fake_llm.py: a fake AI model for the tests)
```

## 5. How to Run the Project

**Requirements:** Python 3.10–3.13, PostgreSQL, Stockfish, and (for the AI coach) an API key
for the model you choose (by default an Anthropic key).

### 5.1 Get the code and install the packages
```bash
git clone https://github.com/ayhamabualhaj/Chess_Coach.git
cd Chess_Coach
python3.13 -m venv .venv             # any Python 3.10–3.13
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
If your system Python is 3.14, install 3.13 first (Fedora: `sudo dnf install python3.13`).

### 5.2 Install Stockfish
Stockfish is a separate program, not a Python package. Install it and note its path:

| System | Install | Path for `STOCKFISH_PATH` |
|---|---|---|
| Fedora | `sudo dnf install stockfish` | `/usr/bin/stockfish` |
| Ubuntu / Debian | `sudo apt install stockfish` | `/usr/games/stockfish` |
| macOS (Homebrew) | `brew install stockfish` | `/opt/homebrew/bin/stockfish` (Apple chip) or `/usr/local/bin/stockfish` |
| Windows | download from https://stockfishchess.org/download/ and unzip | full path to the `.exe` |

Check it: run `stockfish`, type `uci` → it answers `uciok`; type `quit`.
On Linux/macOS, `which stockfish` prints the path.

### 5.3 Create the PostgreSQL database
```bash
sudo -u postgres psql
```
```sql
CREATE USER chess_user WITH PASSWORD 'choose-a-password';
CREATE DATABASE chess_coach OWNER chess_user;
\q
```

### 5.4 Create your `.env`
```bash
cp .env.example .env
```
Fill in the values (see section 6). To generate a `SECRET_KEY`:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5.5 Set up the database tables and an admin user
```bash
python manage.py migrate             # also creates the API token table
python manage.py createsuperuser     # optional, for /admin/
```

### 5.6 Run the app (two terminals)
```bash
# Terminal 1 — the website
python manage.py runserver

# Terminal 2 — the background worker (runs Stockfish analyses and AI reports)
python manage.py db_worker
```
Open http://127.0.0.1:8000, sign up (enter your Lichess name so your side is detected),
upload games, click **Analyse**, then go to **Coaching**.

### 5.7 Run the tests
```bash
python manage.py test tests          # 209 tests; Stockfish tests are skipped if it isn't installed
```
The tests never call a real AI model: the crew and flow run with a fake model
(`tests/fake_llm.py`), so the tests need no API key and cost nothing.

### 5.8 Useful commands
```bash
python manage.py analyse_game <game_id> [--depth N]      # analyse one stored game in the terminal

# Performance evaluation (accuracy vs Lichess, latency, memory per game):
python manage.py evaluate evaluation/data/games.pgn --depths 12 18
#   --great-overhead   also measure the extra time of the "Great move" check
#   --repeat N         time every game N times and keep the median
#   --limit N          only the first N games
#   --out FILE         results CSV (default docs/evaluation_results.csv, summary next to it as .txt)
```
Results of our run (10 games, Stockfish 18): `docs/evaluation_results.csv` / `.txt`,
explained in the performance report `docs/Chess_Coach_Performance_Report.docx`.

## 6. Environment Variables / Secrets

All settings are read from a `.env` file in the project root (loaded with `python-dotenv`).
`.env` is listed in `.gitignore` and must **never** be committed or shared: it contains your
database password and your AI API key. `.env.example` lists every variable with a
placeholder value.

| Variable | Required | Example / default | Meaning |
|---|---|---|---|
| `SECRET_KEY` | yes | long random string | Django's secret for sessions and CSRF (see 5.4) |
| `DEBUG` | no | `True` / default `False` | `True` only for local development |
| `DB_NAME` | yes | `chess_coach` | PostgreSQL database name |
| `DB_USER` | yes | `chess_user` | PostgreSQL user |
| `DB_PASSWORD` | yes | — | that user's password |
| `DB_HOST` | no | `localhost` | database server |
| `DB_PORT` | no | `5432` | database port |
| `STOCKFISH_PATH` | yes* | `/usr/bin/stockfish` (default) | path to the Stockfish program (see 5.2) |
| `STOCKFISH_DEPTH` | no | `12` | search depth per position; higher = stronger but slower |
| `MAX_ANALYSIS_QUEUE` | no | `10` | how many games one user may have waiting for analysis at once |
| `AI_MODEL` | no | `anthropic/claude-sonnet-5-5` (default) | the coach's model as `provider/model`, e.g. `anthropic/claude-haiku-5-5`, `anthropic/claude-opus-5-5`, `openai/gpt-4o-mini` |
| `AI_API_KEY` | for coaching | `sk-ant-...` | the API key for that provider (Anthropic: https://console.anthropic.com); without it everything works except AI reports |

\* Only if Stockfish is not at the default path.

CrewAI's anonymous usage data (telemetry) is switched off in `config/settings.py`.

**Costs.** A report is a few model requests. Measured on a 43-game report (about 12,000 input
and 3,000 output tokens): about 5 cents with Claude Sonnet 5.5 ($2 / $10 per million input /
output tokens), about 10 cents with Claude Opus 5.5 ($4 / $20) and well under one cent with
Claude Haiku 5.5 ($0.10 / $0.50).