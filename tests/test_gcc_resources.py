"""Regional resource coverage must not introduce location preferences."""
import pytest

from job_agent.cli import parse_args
from job_agent.plan import make_plan
from job_agent.records import normalize


REGIONAL = {
    "bayt": "bayt.com", "naukrigulf": "naukrigulf.com",
    "gulftalent": "gulftalent.com", "gulfjobs": "gulfjobs.com",
    "foundit_gulf": "founditgulf.com", "qatar_living": "qatarliving.com",
    "dubizzle": "dubizzle.com",
}


def test_default_budget_reaches_new_sources_for_every_role():
    roles = [f"Synthetic Role {i}" for i in range(8)]
    plan = make_plan({}, roles, ["Qatar"], max_tasks=parse_args(["prepare"]).max_tasks)
    assert len(plan["tasks"]) == plan["total_possible_tasks"]
    for source, domain in REGIONAL.items():
        tasks = [t for t in plan["tasks"] if t["source"] == source]
        assert {t["role"] for t in tasks} == set(roles)
        assert all(f"site:{domain}" in t["query"] and '"Qatar"' in t["query"] for t in tasks)


def test_new_resources_do_not_change_location_or_explicit_budget():
    plan = make_plan({}, ["Data Analyst"], ["India"])
    assert plan["locations"] == ["India"]
    for task in plan["tasks"]:
        if task["source"] in REGIONAL:
            assert '"India"' in task["query"]
            assert not any(country in task["query"] for country in ("Qatar", "Saudi Arabia", "UAE", "GCC"))
    assert len(make_plan({}, ["Data Analyst"], ["Qatar"], max_tasks=5)["tasks"]) == 5


@pytest.mark.parametrize("domain", REGIONAL.values())
def test_regional_listing_hosts_recognized_and_homepages_rejected(domain):
    # Synthetic paths: no live vacancy or posting-date claims.
    item = {"task_id": "q001", "title": "Data Analyst", "snippet": "Synthetic public listing evidence",
            "result_url": f"https://www.{domain}/listing/synthetic-123"}
    assert normalize(item, {"q001"})["url_status"] == "unknown"
    with pytest.raises(ValueError, match="individual listing"):
        normalize({**item, "result_url": f"https://www.{domain}/"}, {"q001"})
