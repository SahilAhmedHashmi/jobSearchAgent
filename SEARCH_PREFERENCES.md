# Search preferences specification

These are generic workflow defaults. Collect fresh answers from every user on every run; this file must never contain personal preferences or candidate data.

## Priorities

- Filter for resume fit, then rank by verified posting recency first. Use match score and the current user's role/work-mode priorities to break date ties.
- Broad coverage is a close second priority.
- Established freshness rule for every run: first few hours (up to 3 hours), first day, first week, then first month, newest verified posting first within each group. Apply this rule without asking the user to repeat it; honor a requested narrower window.
- An hourly tier requires an explicitly evidenced, timezone-aware posting timestamp. A date alone is labeled with date-only precision, never as within a few hours.
- Exclude postings older than 30 days from the qualifying-result count.
- Results with an unverified posting date belong in a separate `date unknown` section and do not count toward the qualifying-result limit.
- Search every selected source for the freshest tier before moving to older tiers.

## Candidate interpretation

- Parse the full resume: dated employment, responsibilities, achievements, projects, education, skills, and inferred experience.
- Infer the candidate's experience level from dated resume roles.
- Allow roles requiring up to one additional year beyond inferred experience; label the gap as a stretch.
- Exclude clear mandatory qualification mismatches.
- Keep learnable skill gaps and explain them.
- Infer related titles from the resume and responsibilities automatically, while allowing the user to add or replace roles.

## Per-run questions

Before each search, ask for these inputs one question at a time. Wait for each reply and understand and validate it before asking the next unanswered question. Clarify unclear answers before proceeding, and skip inputs already supplied in this run. Never send this list as a bundled questionnaire:

- current-run resume attachment or original external file path;
- external destination folder for final results (required, no default);
- target roles;
- employment type: full-time, contract, internship, part-time, or a combination;
- target locations;
- remote/hybrid/on-site/any preference;
- willingness to relocate;
- optional minimum salary;
- desired number of qualifying results (default target 20, larger counts encouraged, no 50-result cap);
- apply the established 30-day freshness rule without a repeat question, unless the user requests a change.

Never reuse previous choices or a previous resume. The user can suggest a different role at any time. Resume text and profile stay in runtime memory only; saved external reports contain listing evidence and scores, not candidate data.

## Source and company research

- Use the built-in web search and page-opening tools, plus any available public browser capability for JavaScript-heavy pages and Apply redirects.
- Do not sign in, use paid search APIs, scrape HTML, or submit applications.
- For TopStartups and IPOPlatform, prioritize companies showing hiring signals and matching the strongest candidate roles.
- Check at most 100 companies on each platform and stop after 20 positive companies on that platform.
- A positive company has at least one verified job satisfying fit, experience, freshness, location, and employment filters.
- Follow up promising IPO/company leads with targeted employer-career searches.

## Matching and repeat searches

- Explain resume fit, skill gaps, and experience gaps in the active conversation only. Export public listing requirements, posting-date evidence, salary when available, links, and provisional match scores.
- Use the employer's original posting date when it conflicts with a board date; flag the board entry as a possible repost.
- Deduplicate only within this run. Do not store or load cross-run history or application events.
- If the user supplies exclusions for this run, apply them only in memory.

## Evidence

- Preserve the individual listing URL and exact search snippet.
- Mark a page `opens`, `redirects`, `blocked`, `closed`, or `unknown` only from observed behavior.
- Record application and employer/ATS redirect URLs only when observed.
- Never infer a posting date from a page crawl age alone.
