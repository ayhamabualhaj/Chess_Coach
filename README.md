# Chess_Coach

**Ayham Abu-Alhaj – Final project, Data Science & AI**

A web app that turns your own chess games into personal coaching. You upload games (PGN),
the Stockfish engine analyses every move, and an AI coach built on Claude finds your
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
3. **AI coach (agent).** You choose games; a **diagnosis agent** (Claude, via the Anthropic API)
   works through your moves with tools: it asks for statistics, opening results, your worst
   moves and re-checks single positions, decides itself what to look at next, and finishes with
   a structured report: 2-4 recurring weaknesses, each with evidence (real moves from your games),
   how to improve and exercises. The agent cannot invent games: answers citing unknown game ids
   are rejected and it has to correct them.
4. **Practice.** For every type of mistake you made, the report links a matching Lichess puzzle
   theme (3 puzzles per mistake), with a tick-off list and a progress bar.
5. **Evaluation.** A command measures the analysis against Lichess's own labels
   (precision / recall / F1) together with latency and memory per game.

**AI component — more than a single API call.** The diagnosis agent is a tool-use loop
(`ai/agents/diagnosis_agent.py`): Claude receives tool definitions, calls tools, gets the
results back and decides the next step, for several turns, until it submits a diagnosis that
passes validation. All statistics come from code (`ai/tools/`), so every number in the report
is grounded in the real analysis.

**APIs used and exposed**

| Used | Purpose |
|---|---|
| Anthropic Claude API (Messages API with tool use) | the diagnosis agent |
| Stockfish via the UCI protocol (python-chess) | move evaluation |
| Lichess puzzle themes (`lichess.org/training/<theme>`) | practice links in the report |
| Lichess game export (with computer analysis) | reference labels for the evaluation |

| Exposed (JSON, login required) | Returns |
|---|---|
| `GET /games/<id>/status/` | analysis status of one game |
| `GET /games/queue/` | how many of your games are being analysed |
| `GET /coaching/reports/<id>/status/` | status of a coaching report |

The pages use these endpoints to refresh themselves while background work is running.

## 3. Technologies Used

| Area | Technology |
|---|---|
| Language | Python 3.10+ (developed on 3.14) |
| Web framework | Django 6.1 (server-rendered templates) |
| Database | PostgreSQL (driver `psycopg2-binary`) |
| Background jobs | Django's built-in Tasks framework + `django-tasks-db` (worker: `python manage.py db_worker`) |
| Chess engine | Stockfish (separate program, tested with versions 16 and 18) |
| Chess logic | `chess` (python-chess): PGN parsing, board rules, UCI engine communication |
| AI | Anthropic Python SDK (`anthropic`), Claude Haiku 5.5 by default (Claude Opus 5.5 supported) |
| Front end | Bootstrap 5.3 (dark theme), Chart.js 4.4 for the evaluation graph |
| Configuration | `python-dotenv` (`.env` file) |
| Tests | Django test runner / `unittest` (194 tests) |

**Architecture.** Each request goes **View → Service → Repository / AI → Database**:
views only handle the request and response, services contain the logic, repositories are the
only code that touches the ORM, and the `ai/` package contains no Django or database code at all
(so the engine, the rules and the agent can be tested on their own). Each model has its own file.

## 4. Project Structure

```
Chess_Coach/
├── manage.py
├── requirements.txt
├── .env.example                 # template for your .env (secrets are never committed)
├── config/                      # Django settings and root URLs
├── apps/
│   ├── accounts/                # sign-up / login, UserProfile (rating, Lichess name)
│   │   ├── models/  repositories/  services/  views/  forms.py  urls.py
│   ├── games/                   # upload, Stockfish analysis, game pages
│   │   ├── models/              # game.py, move.py, mistake.py (one model per file)
│   │   ├── repositories/        # game_repository.py, analysis_repository.py
│   │   ├── services/            # pgn_import_service, analysis_service, game_service
│   │   ├── views/  urls.py  tasks.py (background analysis)
│   │   └── management/commands/ # analyse_game, evaluate
│   └── coaching/                # weakness reports, practice list
│       ├── models/              # weakness_report.py, training_plan.py
│       ├── repositories/  services/  views/  urls.py  tasks.py
├── ai/                          # pure Python: no Django, no database
│   ├── engine/                  # stockfish_wrapper, move_classifier (Lichess rules),
│   │                            # move_types (Brilliant…Blunder), accuracy
│   ├── tools/                   # motif_tools, stats_tools, practice_tools (the agent's tools)
│   └── agents/diagnosis_agent.py  # the Claude tool-use loop
├── evaluation/                  # performance measurement (accuracy, latency, memory)
│   ├── measure_accuracy.py  measure_latency.py  measure_memory.py  run_evaluation.py
│   └── data/games.pgn           # 10 Lichess-analysed test games
├── templates/                   # HTML (base, accounts, games, coaching)
├── static/css/style.css
├── docs/                        # evaluation results (CSV + summary) and the performance report
└── tests/                       # 194 tests
```

## 5. How to Run the Project

**Requirements:** Python 3.10 or newer, PostgreSQL, Stockfish, and (for the AI coach) an
Anthropic API key.

### 5.1 Get the code and install the packages
```bash
git clone https://github.com/ayhamabualhaj/Chess_Coach.git
cd Chess_Coach
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

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
python manage.py migrate
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
python manage.py test tests          # 194 tests; Stockfish tests are skipped if it isn't installed
```
The tests never call the real AI (they use a fake client), so they cost nothing.

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
database password and your Anthropic API key. `.env.example` lists every variable with a
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
| `ANTHROPIC_API_KEY` | for coaching | `sk-ant-...` | key from https://console.anthropic.com; without it everything works except AI reports |
| `ANTHROPIC_MODEL` | no | `claude-haiku-5-5` (default) | Claude model for the coach, e.g. `claude-opus-5-5` |

\* Only if Stockfish is not at the default path.

**Costs.** Each AI report is a few Claude API calls. With the default Claude Haiku 5.5
($0.10 / $0.50 per million input / output tokens) a report costs well under one cent;
with Claude Opus 5.5 ($4 / $20 per million tokens) roughly 5–15 cents.