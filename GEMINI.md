# Gemini fresh-run workflow

Apply the established freshness rule in AGENTS.md without asking it again: last 30 days, newest verified postings first, first few hours / first day / first week / first month. Hourly claims require timestamp evidence. Other intake answers remain fresh for each run.

Follow [AGENTS.md](AGENTS.md) and its mandatory fresh intake on every run: current resume, external output folder, roles, employment type, locations/work mode/relocation, optional salary, freshness and result count (default 20, larger requests supported).

Ask exactly one intake question at a time in the order in AGENTS.md. Wait for the user's answer, understand and validate it, then ask the next unanswered question. Ask locations, work mode and relocation separately. Clarify an unclear answer before advancing; skip answers already supplied for this run. Never present a bundled questionnaire or start searching with incomplete intake.

Keep resume/profile and intermediate plans/results in runtime memory only. No project data folder or history database. Use the stdout prepare / stdin import interface in README.md; export only to the user-selected external folder. Do not reuse previous run data. If built-in live web search is unavailable, explain the limitation instead of fabricating listings.
