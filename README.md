# Resume Job Agent — fresh, runtime-only searches

Run this project inside a Codex or Gemini session with built-in live web search. Say **“Run this project”**. The agent follows [AGENTS.md](AGENTS.md) and starts a new intake every time:

The agent asks **one question at a time**, waits for your reply, and checks it before moving to the next question. It clarifies unclear answers and skips anything you already supplied for this run. Locations, work mode and relocation are separate questions. Search begins only after the required answers are collected. The intake covers:

- Provide your resume for this run, as an attachment or an original file outside this project.
- Choose a folder outside the project for the final results.
- Choose roles, employment types, locations, work modes and relocation preference.
- Set an optional minimum annual salary, freshness window and desired result count.

The default target is **20 qualifying jobs**. You can request 50, 100, or another positive count. Verified availability and evidence determine how many can actually be delivered; missing results are never invented. Undated listings are shown separately and do not consume the requested count.

## Privacy and storage

The established freshness rule applies automatically on future runs: search the last 30 days, then show the newest verified postings first, grouped into the first few hours (up to 3 hours), first day, first week and first month. Match relevance breaks date ties. Hourly labels require an explicit posting timestamp; date-only listings retain an honest precision label. You can request a narrower window. Other preferences and the resume are collected fresh each run.

The resume is read from its original location and never copied. Resume text, hashes, education, work history and candidate profiles exist only during processing. Preparation writes no files. Plans and collected search results pass through runtime memory and standard input.

Only the final HTML, CSV and JSON reports are saved, in a new timestamped subfolder of the **external folder you chose**. Reports contain listing evidence and provisional match scores, without candidate profiles or resume-specific fit explanations. Detailed candidate comparisons belong in the active conversation only. No data folder, intermediate files, saved preferences, backups or history database are created by the project. Every run starts fresh, including repeat searches.

Project-local resume and report paths are rejected, including paths resolving through a symlink/junction into the project. Keep your source resume outside the repository. The coding-agent host may retain conversations, attachments or tool logs according to its own settings; this project cannot erase or control those records.

## Setup

Python 3.10+ is supported. PDF/DOCX input needs the dependencies below; scanned PDFs require OCR beforehand.

```powershell
python -m pip install -e ".[dev]"
python -B -m pytest -q -p no:cacheprovider
```

Use only synthetic data for development. Tests create their temporary fixtures outside the project.

## Agent workflow

After collecting the current user's answers, run:

```powershell
python -B main.py prepare --resume "D:\Private\resume.pdf" --output-dir "D:\JobSearchResults" --roles "Data Analyst,Reporting Analyst" --location India --employment-type full-time --work-mode any --relocate yes --days 30 --result-limit 50
```

The command emits a **resume-free plan to stdout**. Hold it in memory; do not redirect it to a file. Optional flags: `--salary-min`, `--max-tasks` (default 209, covering eight roles across all sources; derived from the source registry), `--no-ipo`. A terminal user can run `python -B main.py` to answer the intake prompts; this prepares a plan but cannot invoke an agent's private search tool.

Execute the plan using the agent's built-in search/open tools. Preserve individual listing URLs and posting-date evidence according to AGENTS.md. Keep the result batch in memory. Feed this envelope through stdin:

```json
{
  "plan": {"...": "the resume-free object printed by prepare"},
  "results": {"schema_version": 1, "source_health": [], "results": []}
}
```

Use `python -B main.py import --resume "D:\Private\resume.pdf" --output-dir "D:\JobSearchResults"`. Supply the envelope directly through a pipe/stdin, without a staging file. The output folder must match the folder selected in the plan. Invalid batches produce errors without writing reports; correct the in-memory batch and retry.

The importer reads the original resume into memory for ranking. It exports `report.html`, `report.csv` and `report.json` in the external destination and reports the dated count versus the target. The JSON separates `opportunities` from `date_unknown` and `company_leads`. There are no history/event commands and no cross-run deduplication.

## Search coverage

Workday, Greenhouse, Lever, Ashby, Workable, SmartRecruiters, iCIMS, Jobvite, employer sites, TopStartups, LinkedIn, Indeed, Naukri, Wellfound and Foundit. IPOPlatform supplies company leads only; IPO activity is not proof of hiring.

Additional GCC discovery resources (official job pages checked October 2026):

| Resource | Coverage / official discovery page |
| --- | --- |
| Bayt | [Middle East job search](https://www.bayt.com/en/international/jobs/search/) |
| Naukrigulf | [UAE, Saudi Arabia, Qatar, Oman, Kuwait and Bahrain](https://www.naukrigulf.com/jobs-by-location) |
| GulfTalent | [Regional job board](https://www.gulftalent.com/) |
| GulfJobs | [All six GCC countries](https://www.gulfjobs.com/jobs-by-location) |
| foundit Gulf | [Gulf job board, formerly Monster Gulf](https://www.founditgulf.com/) |
| Qatar Living | [Qatar job listings](https://www.qatarliving.com/en/jobs) |
| Dubizzle | [UAE classifieds job section](https://dubai.dubizzle.com/jobs/) |

These are discovery resources, not reportable individual listings. Search tasks use only the locations selected in the current intake; adding a source does not select GCC countries or change any intake question/default. Regional boards can return locations outside the selection, so validate each listing's location. Broad domain searches accommodate country subdomains and localized listing paths. For classifieds, confirm that each result is an actual job advertisement. Open individual listings and retain the existing date, salary and application-link evidence requirements. Access can vary by listing; record blocked pages in source health rather than bypassing restrictions.

No paid search API, scraping, browser automation, account login or application submission. Blocked and unavailable sources are reported honestly. Search crawl ages never count as posting dates. Unknown job details stay unknown. Match scores are provisional relevance, not eligibility certification or hiring probability.

## Sharing the repository

The root `.gitignore` uses a source-file allowlist and excludes data, reports, plans, resumes, databases, secrets, archives, logs and caches. New source files outside the allowed paths need a deliberate ignore-rule update. All examples and tests must stay synthetic. Never put real resumes or results in source code or documentation.

Before publishing, inspect `git status --short`, `git ls-files`, and `git diff --cached`. Ignore rules do **not** remove files already tracked or erase past commits. If private data was previously committed, remove it from the index and clean the affected Git history before sharing; check any existing remote separately. Never force-add personal files.

## Code map

- `cli.py`: fresh intake, stdout plan and stdin import
- `privacy.py`: external-path checks
- `resume.py`: runtime ingestion and conservative profiling
- `plan.py`: bounded discovery tasks
- `records.py`: evidence validation
- `ranking.py`: current-run deduplication and ranking
- `reporting.py`: external, candidate-free reports

All Python modules are under `job_agent/`.
