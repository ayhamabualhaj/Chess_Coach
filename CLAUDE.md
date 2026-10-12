# Chess_Coach — project context for Claude

University final project (Data Science & AI). Django web app: users upload chess games (PGN),
Stockfish analyses every move, an agentic AI layer turns recurring mistakes into a report and
a training plan. Grading rules: see the course PDF (Django + PostgreSQL, one major AI component
that is more than a single API call, one model per file, views split per area,
View -> Service -> Repository / ai -> DB, APIs used and exposed, web UI, performance report with
accuracy + latency + memory per test case, README with 6 sections, .env/.env.example/.gitignore,
final presentation).

## Environment
Fedora, PyCharm, Python 3.14, venv `.venv/`, Django 6.1.2, PostgreSQL db `chess_coach`
(owner `chess_user`), Stockfish 18 at /usr/bin/stockfish. Branch `master`, push via SSH.

## Conventions
- Views only handle request/response and call services.
- Services hold business logic; they call repositories and `ai/`.
- Repositories are the only code that touches the ORM.
- `ai/` has no Django or DB code.
- Each model in its own file, re-exported in `models/__init__.py`.
- After `pip install`: `pip freeze > requirements.txt`.
- One feature per step, tested, then committed and pushed.

## Working style (student preferences)
- Explain each step briefly; one small step at a time; cite checked sources; honest claims.
- Terminal commands only to create empty files/folders (`mkdir -p`, `touch`).
- Code is given as normal code blocks with the file path; give full files when edits are fiddly.
- Give the git commit message after every step.

## Done (Steps 6–14)
- Accounts: UserProfile (rating 100–3500, lichess_username), signup/login/logout, Bootstrap dark theme.
- Games: Game (white/black/result, status pending/queued/running/done/failed, analysis_error),
  Move (ply, color, san, uci, fen_before, eval_before/after in cp from White's view, best_move_uci,
  cp_loss), Mistake (OneToOne Move, severity, phase, motif).
- `ai/engine/`: StockfishEngine wrapper (fixed depth, 1 thread, MATE_SCORE 10000);
  move_classifier.py = Lichess rules (win-chance formula, 0.1/0.2/0.3 thresholds, mate rules,
  cp ceiling 1000) copied from lila Advice.scala + scalachess eval.scala; game_phase().
- Analysis service + `analyse_game <id> [--depth N]` command; runs in background with Django
  Tasks + django-tasks-db (`python manage.py db_worker` in a 2nd terminal).
- Game page: Analyse button, status polling via /games/<id>/status/ (JSON), per-side ACPL and
  mistake counts, Chart.js eval graph, move table with highlights and best move.
- `ai/tools/`: motif_tools.py (allowed/missed mate, hanging piece, missed fork/capture/check,
  engine-based forced mates), stats_tools.py (MoveRecord, summarize_mistakes, opening_breakdown,
  worst_moves, opening_label). Motifs are saved on each Mistake during analysis.
- 88 tests passing (`python manage.py test tests`).

## Findings for the performance report
- Opera Game, depth 12: 1.4 s, 15.Bxd7+ wrongly labelled a blunder (horizon effect);
  depth 20: 83.6 s, label disappears. Results depend on engine version + depth.

## Next steps
15. Diagnosis agent (LLM tool-use loop over ai/tools) — needs AI provider choice + API key in .env.
16. WeaknessReport + TrainingPlan models. 17. Coach agent + coaching service. 18. Coaching UI.
19. REST API (DRF, token auth). 20. Lichess import by username (optional).
21–24. Evaluation dataset (Lichess games with [%eval]), accuracy vs Lichess labels
    (precision/recall/F1), latency + memory per test case, depth trade-off improvements.
25–27. README, final cleanup, performance document + presentation, submit via Classroom.
Known tidy-up: duplicate imports at top of apps/games/services/game_service.py.