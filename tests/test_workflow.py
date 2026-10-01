import json
from pathlib import Path

from job_agent.plan import make_plan
from job_agent.ranking import rank
from job_agent.records import clean_url, load_batch, normalize
from job_agent.reporting import write_reports
from job_agent.resume import profile


def setup():
    p = profile("Alex Data Analyst with 1 year of experience using Python and SQL. MCA graduate.", "test")
    return make_plan(p, ["Data Analyst"], ["India"], days=7)


def job(task):
    return {"task_id": task, "kind": "job", "title": "Data Analyst job", "company": "Example",
            "location": "India", "snippet": "Data Analyst role in India. Python SQL.",
            "result_url": "https://jobs.lever.co/example/analyst", "application_url": None,
            "posting_date": None, "search_page_date": "2026-09-25", "url_status": "unknown"}


def test_plan_has_ats_and_company_leads():
    plan = setup()
    assert any(x["source"] == "workday" for x in plan["tasks"])
    assert any(x["source"] == "topstartups" for x in plan["tasks"])
    assert all(any(x["source"] == source for x in plan["tasks"]) for source in ("indeed_india", "naukri", "wellfound", "foundit"))
    assert any(x["source"] == "ipoplatform" and x["expected"].startswith("company leads") for x in plan["tasks"])


def test_page_date_not_posting_date_and_relevance():
    plan = setup()
    normalized = normalize(job(plan["tasks"][0]["id"]), {x["id"] for x in plan["tasks"]})
    found, leads = rank([normalized], plan)
    assert len(found) == 1 and not leads
    assert found[0]["posting_age_days"] is None
    assert found[0]["freshness_label"] == "posting date unknown"


def test_rejects_unproven_application_and_unsafe_urls():
    plan = setup()
    data = job(plan["tasks"][0]["id"])
    data["application_url"] = "https://employer.com/apply"
    try:
        normalize(data, {x["id"] for x in plan["tasks"]})
        assert False, "should reject ungrounded application URL"
    except ValueError:
        pass
    for url in ("http://127.0.0.1/private", "https://user:pass@example.com/", "file:///etc/passwd"):
        try:
            clean_url(url)
            assert False, url
        except ValueError:
            pass


def test_import_reports_and_escaping(tmp_path):
    plan = setup()
    raw = job(plan["tasks"][0]["id"])
    raw["snippet"] = '<script>alert(1)</script> Python SQL India'
    resultfile = tmp_path / "results.json"
    resultfile.write_text(json.dumps({"schema_version": 1, "results": [raw, {"bad": True}]}))
    jobs, errors, health = load_batch(str(resultfile), plan)
    matches, leads = rank(jobs, plan)
    out = write_reports(str(tmp_path / "report"), plan, matches, leads, errors, health)
    page = (out / "report.html").read_text()
    assert "<script>alert" not in page and "&lt;script&gt;" in page
    assert len(errors) == 1
