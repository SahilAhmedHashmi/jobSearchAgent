"""Regression coverage for the documented operator and CLI contract."""
import json

import pytest

from job_agent.cli import main
from job_agent.plan import make_plan
from job_agent.records import load_batch, normalize
from job_agent.reporting import safe_cell
from job_agent.ranking import rank


def listing(**changes):
    return {"task_id": "q001", "title": "Data Analyst job", "kind": "job",
            "snippet": "Python SQL in India", "result_url": "https://jobs.lever.co/acme/123",
            **changes}


def test_bounded_plan_covers_roles_and_real_company_search():
    plan = make_plan({}, ["Data Analyst", "Software Engineer"], ["India", "Assam"], max_tasks=5)
    assert len(plan["tasks"]) == 5
    assert {t["role"] for t in plan["tasks"][:2]} == set(plan["roles"])
    assert all(t["source"] == "open_web" for t in plan["tasks"][:2])
    assert '("India" OR "Assam")' in plan["tasks"][0]["query"]
    full = make_plan({}, ["Data Analyst"], [])
    assert all("site:" not in t["query"] for t in full["tasks"] if t["source"] == "company")
    with pytest.raises(ValueError):
        make_plan({}, [" "], [])


def test_original_evidence_preserved_but_identity_ignores_tracking():
    original = "https://jobs.lever.co/acme/123?utm_source=search#apply"
    first = normalize(listing(result_url=original, snippet="X" * 1400), {"q001"})
    second = normalize(listing(), {"q001"})
    assert first["result_url"] == original
    assert len(first["snippet"]) == 1400
    assert first["id"] == second["id"]
    assert first["checked_at"] is None
    assert first["url_status"] == "unknown"


@pytest.mark.parametrize("changes", [
    {"url_status": "opens"},
    {"url_status": "redirects", "checked_at": "2026-09-25T12:00:00+05:30"},
    {"checked_at": "yesterday"},
    {"checked_at": "2026-09-25T12:00:00"},
    {"application_url_source": "browser_observed"},
    {"application_url": "https://acme.com/jobs/123", "application_url_source": "search_result"},
    {"result_url": "https://www.ipoplatform.com/ipo/acme"},
    {"result_url": "https://topstartups.io/jobs/"},
    {"task_id": []},
])
def test_invalid_evidence_is_rejected(changes):
    with pytest.raises(ValueError):
        normalize(listing(**changes), {"q001"})


def test_observed_redirect_is_retained():
    result = normalize(listing(url_status="redirects", checked_at="2026-09-25T12:00:00+05:30",
                               redirect_url="https://acme.com/jobs/123?utm_source=lever"), {"q001"})
    assert result["redirect_url"].endswith("?utm_source=lever")


def test_invalid_batch_is_actionable(tmp_path):
    path = tmp_path / "results.json"
    path.write_text("[]")
    with pytest.raises(ValueError, match="results array"):
        load_batch(str(path), {"tasks": []})



def test_csv_preserves_zero_and_neutralizes_formulas():
    assert safe_cell(0) == "0"
    for value in ("=1+1", "  @SUM(1)", "\ttext", "\rtext", "\ntext"):
        assert safe_cell(value).startswith("'")


def test_resume_profile_infers_dated_experience_and_related_roles():
    from job_agent.resume import profile
    candidate = profile("Data Analyst | Example | June 2025 – Present\nAI/ML Researcher | NIELIT Jan 2025 – May 2025\nPython SQL Power BI", "x")
    assert candidate["experience_years"] is not None
    assert candidate["experience_basis"] == "dated resume roles"
    assert "reporting analyst" in candidate["related_role_suggestions"]


def test_plan_carries_search_preferences():
    plan = make_plan({}, ["Data Analyst"], ["India"], employment_types=["full-time"],
                     work_modes=["remote"], salary_min=500000, result_limit=12)
    assert plan["freshness_tiers_days"] == [0, 1, 7, 30]
    assert plan["salary_min"] == 500000
    assert plan["result_limit"] == 12


def test_rank_assigns_freshness_and_experience_status():
    plan = make_plan({"skills": ["python", "sql"]}, ["Data Analyst"], ["India"])
    plan["profile"]["experience_years"] = 1
    plan["result_limit"] = 3
    raw = listing(task_id=plan["tasks"][0]["id"], location="India")
    raw.update({"posting_date": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).date().isoformat(), "posting_date_source": "platform_label", "experience_required_years": 2,
                "checked_at": "2026-09-25T12:00:00+05:30", "url_status": "opens"})
    normalized = normalize(raw, {x["id"] for x in plan["tasks"]})
    found, _ = rank([normalized], plan)
    assert found[0]["freshness_tier"] == "today (time unknown)"
    assert found[0]["experience_status"].startswith("stretch")


def test_newer_posting_beats_better_match_in_same_week():
    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone.utc).date()
    plan = make_plan({"skills": ["python", "sql"]}, ["Data Analyst"], ["India"], days=30)
    older = normalize(listing(posting_date=(today - timedelta(days=6)).isoformat(),
                              posting_date_source="platform_label"), {"q001"})
    newer = normalize(listing(title="Reporting Analyst job", snippet="Reporting role",
                              result_url="https://jobs.lever.co/acme/newer",
                              posting_date=(today - timedelta(days=4)).isoformat(),
                              posting_date_source="platform_label"), {"q001"})
    found, _ = rank([older, newer], plan)
    assert found[0]["id"] == newer["id"]
    assert found[0]["score"] < found[1]["score"]


def test_hourly_order_and_labels_require_timestamp_evidence():
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    plan = make_plan({}, ["Data Analyst"], ["India"], days=30)
    jobs = []
    for hours in (4, 1):
        posted = now - timedelta(hours=hours)
        jobs.append(normalize(listing(result_url=f"https://jobs.lever.co/acme/{hours}",
                                      posting_date=posted.date().isoformat(),
                                      posting_date_source="platform_label",
                                      posting_timestamp=posted.isoformat()), {"q001"}))
    found, _ = rank(jobs, plan)
    assert found[0]["freshness_tier"] == "within first few hours (3 hours)"
    assert found[1]["freshness_tier"] == "within 24 hours"
    date_only = normalize(listing(posting_date=now.date().isoformat(),
                                  posting_date_source="platform_label"), {"q001"})
    assert rank([date_only], plan)[0][0]["freshness_tier"] == "today (time unknown)"


@pytest.mark.parametrize("timestamp", ["2026-09-25T12:00:00", "invalid", "2026-09-24T12:00:00Z"])
def test_invalid_posting_timestamp_is_rejected(timestamp):
    with pytest.raises(ValueError, match="posting_timestamp"):
        normalize(listing(posting_date="2026-09-25", posting_date_source="platform_label",
                          posting_timestamp=timestamp), {"q001"})


def test_multiple_search_filters_are_alternatives():
    plan = make_plan({}, ["Data Analyst"], ["India"], employment_types=["full-time", "contract", "internship"],
                     work_modes=["on-site", "remote"])
    query = plan["tasks"][0]["query"]
    assert '("full-time" OR "contract" OR "internship")' in query
    assert '("on-site" OR "remote")' in query


def test_salary_floors_by_type_and_unknown_pay_not_counted(tmp_path):
    from datetime import datetime, timezone
    from job_agent.reporting import write_reports
    date = datetime.now(timezone.utc).date().isoformat()
    plan = make_plan({}, ["Data Analyst"], ["India"], days=30)
    plan["salary_min_by_employment_type"] = {"full-time": 540000, "internship": 360000}
    jobs = []
    for index, (employment, salary) in enumerate((('full-time', 500000), ('full-time', 540000),
                                                ('internship', 360000), ('contract', None), ('full-time', None))):
        jobs.append(normalize(listing(result_url=f"https://jobs.lever.co/acme/{index}",
                                      posting_date=date, posting_date_source="platform_label",
                                      employment_type=employment, salary=salary, salary_currency="INR"), {"q001"}))
    found, _ = rank(jobs, plan)
    assert len(found) == 4
    folder = write_reports(tmp_path / "report", plan, found, [], [])
    report = json.loads((folder / "report.json").read_text())
    assert report["qualifying_result_count"] == 3
    assert len(report["salary_unverified"]) == 1


def test_accepted_unknown_salaries_count_in_recency_order(tmp_path):
    from datetime import datetime, timedelta, timezone
    from job_agent.reporting import write_reports
    today = datetime.now(timezone.utc).date()
    plan = make_plan({}, ["Data Analyst"], ["India"], result_limit=2)
    plan["salary_min_by_employment_type"] = {"full-time": 540000}
    plan["include_salary_unverified"] = True
    jobs = [normalize(listing(result_url=f"https://jobs.lever.co/acme/{i}",
                              posting_date=(today - timedelta(days=age)).isoformat(),
                              posting_date_source="platform_label", employment_type=employment,
                              salary=salary, salary_currency="INR"), {"q001"})
            for i, (age, employment, salary) in enumerate(
                [(0, "full-time", 500000), (1, "full-time", None), (2, "contract", None), (3, "full-time", None)])]
    found, _ = rank(jobs, plan)
    assert [j["id"] for j in found] == [jobs[1]["id"], jobs[2]["id"]]
    folder = write_reports(tmp_path / "report", plan, found, [], [])
    report = json.loads((folder / "report.json").read_text())
    assert report["target_met"] is True
    assert report["qualifying_result_count"] == 2
    assert report["salary_verified_or_unrestricted_count"] == 1
    assert report["salary_unverified"][0]["salary_status"] == "unverified"
