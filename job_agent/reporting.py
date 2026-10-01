"""External HTML/CSV/JSON results without resumes or candidate profiles."""
import csv
import html
import json
from .privacy import output_directory

JOB_FIELDS = (
    "id", "task_id", "kind", "title", "company", "location", "platform", "snippet",
    "result_url", "application_url", "application_url_source", "redirect_url", "primary_link",
    "url_status", "checked_at", "posting_date", "posting_timestamp", "posting_date_source", "search_page_date",
    "salary", "salary_currency", "salary_status", "employment_type", "work_mode", "experience_required_years",
    "evidence", "score", "score_label", "freshness_tier", "freshness_label", "posting_age_days",
)


def safe_cell(value):
    s = "" if value is None else str(value)
    return "'" + s if s.startswith(("\t", "\r", "\n")) or s.lstrip().startswith(("=", "+", "-", "@")) else s


def write_reports(folder, plan, matches, leads, errors, health=None):
    path = output_directory(folder)
    # Whitelist listing fields; never serialize runtime candidate or fit explanations.
    matches = [{k: j[k] for k in JOB_FIELDS if k in j} for j in matches]
    leads = [{k: j[k] for k in JOB_FIELDS if k in j} for j in leads]
    dated = [j for j in matches if j.get("posting_date") and j.get("salary_status") != "unverified"]
    salary_unverified = [j for j in matches if j.get("posting_date") and j.get("salary_status") == "unverified"]
    undated = [j for j in matches if not j.get("posting_date")]
    target = plan.get("result_limit") or 20
    accepted_unverified = bool(plan.get("include_salary_unverified"))
    counted = [j for j in matches if j.get("posting_date")] if accepted_unverified else dated
    data = {
        "schema_version": 1,
        "notes": ["Relevance scores are provisional, not hiring probabilities.",
                  "Only explicitly evidenced posting dates count toward the requested total.",
                  "No resume, candidate profile, or cross-run history is saved."],
        "requested_result_count": target, "qualifying_result_count": len(counted),
        "salary_verified_or_unrestricted_count": len(dated),
        "include_salary_unverified": accepted_unverified,
        "target_met": len(counted) >= target, "opportunities": counted,
        "date_unknown": undated, "company_leads": leads,
        "salary_unverified": salary_unverified,
        "rejected_results": errors, "source_health": health or [],
    }
    path.mkdir(parents=True, exist_ok=True)
    # Recheck resolved paths, including existing symlinks at the file level.
    from .privacy import external_path
    files = {ext: external_path(path / ("report." + ext)) for ext in ("json", "csv", "html")}
    for file in files.values():
        if file.exists():
            raise ValueError("Report already exists; choose a fresh run folder")
    files["json"].write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    columns = ["id", "score", "freshness_tier", "title", "company", "location", "posting_date",
               "posting_timestamp", "posting_date_source", "salary", "salary_currency", "salary_status", "employment_type", "work_mode", "experience_required_years",
               "url_status", "result_url", "application_url", "primary_link", "snippet", "evidence"]
    with files["csv"].open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        for job in matches:
            writer.writerow([safe_cell(job.get(k)) for k in columns])

    def cards(jobs):
        output = []
        for job in jobs:
            def e(key):
                value = job.get(key)
                return html.escape("" if value is None else str(value), quote=True)
            output.append(
                f'<article><h3>{e("title")}</h3><p>{e("company")} · {e("location")}</p>'
                f'<p>Relevance {e("score")}/100 · {e("freshness_tier")} · URL {e("url_status")}</p>'
                f'<p>Required experience (years): {e("experience_required_years")}. '
                f'Salary: {e("salary")} {e("salary_currency")} (annual). {e("salary_status")}</p>'
                f'<p>{e("snippet")}</p><p>{e("evidence")}</p>'
                f'<a href="{e("primary_link")}" rel="noopener noreferrer" target="_blank">Open listing/application</a> '
                f'<a href="{e("result_url")}" rel="noopener noreferrer" target="_blank">Original result</a></article>')
        return "".join(output) or "<p>No listings in this section.</p>"

    coverage = "".join("<li>" + html.escape(f"{x['source']}: {x['status']} — {x['note']}") + "</li>" for x in (health or []))
    lead_items = "".join(f'<li><a href="{html.escape(j["result_url"], quote=True)}">{html.escape(j["company"])}</a></li>' for j in leads)
    document = (
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Job search report</title><style>body{font:16px system-ui;max-width:900px;margin:3rem auto;padding:0 1rem}"
        "article{border:1px solid #ccd5e0;border-radius:12px;padding:1rem;margin:1rem 0}</style>"
        f"<h1>Job search results</h1><p>{len(counted)} of {target} requested dated results. "
        f"{len(undated)} additional undated listings; {len(salary_unverified)} dated listings with salary eligibility unverified.</p>"
        "<p>Check requirements and availability before applying. Unknown dates do not count toward the target.</p>"
        "<h2>Dated results, newest first</h2>" + cards(counted)
        + ("<p>Salary-unverified listings count toward this run's target by your choice. Published salaries below the minimum remain excluded.</p>" if accepted_unverified else "<h2>Salary eligibility unverified (not counted toward target)</h2>" + cards(salary_unverified))
        + "<h2>Date unknown</h2>" + cards(undated)
        + "<h2>Source coverage</h2><ul>" + coverage + "</ul>"
        + "<h2>Company leads</h2><p>Company research only; hiring not established.</p><ul>" + lead_items + "</ul></html>"
    )
    files["html"].write_text(document, encoding="utf-8")
    return path
