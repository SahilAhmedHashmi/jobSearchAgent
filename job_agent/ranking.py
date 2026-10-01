"""Provisional ranking from titles and search snippets; missing facts stay unknown."""
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

STOP = {"a", "an", "and", "the", "for", "of", "in", "to", "jobs", "job", "apply", "career", "careers", "at"}


def tokens(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9+#.]+", text.lower()) if x not in STOP and len(x) > 1}


def rank(jobs: list[dict], plan: dict, limit: int = 20) -> tuple[list[dict], list[dict]]:
    roles = plan["roles"]
    skills = plan["profile"].get("skills", [])
    locations = plan.get("locations", [])
    candidate_years = plan["profile"].get("experience_years")
    salary_min = plan.get("salary_min")
    by_key: dict[str, dict] = {}
    leads = []
    for job in jobs:
        if job["kind"] == "company_lead":
            leads.append(job)
            continue
        if job["url_status"] == "closed":
            continue
        if job.get("employment_type") and plan.get("employment_types") and job["employment_type"] not in plan["employment_types"]:
            continue
        if job.get("work_mode") and plan.get("work_modes") and job["work_mode"] not in plan["work_modes"]:
            continue
        type_minima = plan.get("salary_min_by_employment_type", {})
        minimum = type_minima.get(job.get("employment_type"), salary_min)
        salary_status = "not required" if minimum is None else "unverified"
        if type_minima and not job.get("employment_type"):
            salary_status = "unverified"
        if minimum is not None and job.get("salary") is not None and job.get("salary_currency", "").upper() == "INR":
            salary_status = "meets minimum" if job["salary"] >= minimum else "below minimum"
        if salary_status == "below minimum":
            continue
        job = {**job, "salary_status": salary_status}
        key = job["id"]
        if key in by_key:
            old = by_key[key]
            if (bool(job["application_url"]), bool(job["company"]), len(job["snippet"])) > (bool(old["application_url"]), bool(old["company"]), len(old["snippet"])):
                job = {**job, "also_found_at": list(dict.fromkeys(old.get("also_found_at", []) + [old["result_url"]]))}
                by_key[key] = job
            else:
                old.setdefault("also_found_at", []).append(job["result_url"])
            continue
        by_key[key] = {**job, "salary_status": salary_status}
    output = []
    now = datetime.now(timezone.utc)
    for job in by_key.values():
        title = tokens(job["title"])
        body = tokens(job["snippet"])
        role_match = max((len(title & tokens(r)) / max(1, len(tokens(r))) for r in roles), default=0)
        skill_hits = [s for s in skills if tokens(s) <= body | title]
        skill_score = len(skill_hits) / len(skills) if skills else None
        text = (job["location"] + " " + job["snippet"]).lower()
        location_hit = any(loc.lower() in text for loc in locations) if locations else None
        age = None
        posted_at = None
        if job["posting_date"]:
            age = (now.date() - datetime.fromisoformat(job["posting_date"]).date()).days
        if job.get("posting_timestamp"):
            posted_at = datetime.fromisoformat(job["posting_timestamp"].replace("Z", "+00:00"))
            age = (now - posted_at).total_seconds() / 86400
        if age is not None and age > min(plan.get("days", 30), 30):
            continue
        # Search-page dates are deliberately excluded from posting-age scoring.
        freshness = max(0, 1 - age / 30) if age is not None else None
        if age is None:
            freshness_tier = "date unknown"
        elif posted_at is not None and age <= 3 / 24:
            freshness_tier = "within first few hours (3 hours)"
        elif posted_at is None and age <= 0:
            freshness_tier = "today (time unknown)"
        elif age <= 1:
            freshness_tier = "within 24 hours"
        elif age <= 7:
            freshness_tier = "within 7 days"
        elif age <= 30:
            freshness_tier = "within 30 days"
        else:
            continue
        required = job.get("experience_required_years")
        experience_status = "unknown"
        if required is not None and candidate_years is not None:
            try:
                required = float(required)
                experience_status = "within inferred experience" if required <= candidate_years else ("stretch: up to one year above inferred experience" if required <= candidate_years + 1 else "outside experience allowance")
            except (TypeError, ValueError):
                required = None
        if experience_status == "outside experience allowance":
            continue
        score = round(100 * (0.65 * role_match + 0.15 * (skill_score if skill_score is not None else .5)
                            + 0.10 * (1 if location_hit else .5)
                            + 0.10 * (freshness if freshness is not None else .5)))
        job.update({"score": score, "role_alignment": round(role_match * 100),
                    "matched_resume_skills_in_snippet": skill_hits, "location_mentioned": location_hit,
                    "posting_age_days": age, "freshness_tier": freshness_tier,
                    "experience_status": experience_status, "qualification_assessment": "insufficient listing text",
                    "fit_explanation": f"Title alignment {round(role_match * 100)}%; matched skills: {', '.join(skill_hits) or 'none visible in snippet'}.",
                    "skill_gaps": [],
                    "score_label": "provisional search-result relevance, not hiring probability",
                    "freshness_label": "posting date evidenced" if age is not None else "posting date unknown",
                    "primary_link": job["redirect_url"] or job["application_url"] or job["result_url"]})
        if role_match > 0:
            output.append(job)
    # Posting recency precedes relevance, including within a freshness tier.
    def order(job):
        date = datetime.fromisoformat(job["posting_date"]).date() if job["posting_date"] else None
        timestamp = datetime.fromisoformat(job["posting_timestamp"].replace("Z", "+00:00")) if job.get("posting_timestamp") else None
        role_priority = next((i for i, role in enumerate(roles) if tokens(role) <= tokens(job["title"])), len(roles))
        preferred_modes = plan.get("preferred_work_modes", [])
        mode_priority = preferred_modes.index(job["work_mode"]) if job["work_mode"] in preferred_modes else len(preferred_modes)
        return (date is None, -(date.toordinal() if date else 0),
                -(timestamp.timestamp() if timestamp else 0), -job["score"], role_priority, mode_priority, job["id"])
    output.sort(key=order)
    cap = plan.get("result_limit") or limit
    dated = [j for j in output if j["posting_date"] is not None and j["salary_status"] != "unverified"]
    unverified = [j for j in output if j["posting_date"] is not None and j["salary_status"] == "unverified"]
    undated = [j for j in output if j["posting_date"] is None]
    if plan.get("include_salary_unverified"):
        return [j for j in output if j["posting_date"] is not None][:cap] + undated, leads
    return dated[:cap] + unverified + undated, leads
