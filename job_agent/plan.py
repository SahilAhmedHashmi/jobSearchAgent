"""Bounded task generation for an external agent's own web search tool."""
from datetime import datetime, timezone

SITES = {
    "workday": "myworkdayjobs.com", "workday_alt": "workdayjobs.com",
    "greenhouse": "job-boards.greenhouse.io", "greenhouse_legacy": "boards.greenhouse.io",
    "lever": "jobs.lever.co", "ashby": "jobs.ashbyhq.com",
    "workable": "apply.workable.com", "smartrecruiters": "jobs.smartrecruiters.com",
    "icims": "careers.icims.com", "jobvite": "jobs.jobvite.com",
    "topstartups": "topstartups.io/jobs", "linkedin": "linkedin.com/jobs/view",
    "indeed_india": "in.indeed.com/viewjob", "indeed": "indeed.com/viewjob",
    "naukri": "naukri.com/job-listings", "wellfound": "wellfound.com/jobs",
    "foundit": "foundit.in/job", "company": None,
}


def make_plan(profile: dict, roles: list[str], locations: list[str], days: int = 7,
              include_ipo: bool = True, max_tasks: int = 60,
              employment_types: list[str] | None = None, work_modes: list[str] | None = None,
              salary_min: float | None = None, result_limit: int | None = 20) -> dict:
    if not roles or days < 1 or days > 31 or max_tasks < 1:
        raise ValueError("Provide roles, days 1-31, and a positive task limit")
    roles = list(dict.fromkeys(x.strip() for x in roles if x.strip()))[:8]
    if not roles:
        raise ValueError("Select at least one non-empty role")
    locations = [x.strip() for x in locations if x.strip()][:4]
    employment_types = list(dict.fromkeys(x.strip().lower() for x in (employment_types or []) if x.strip()))
    work_modes = list(dict.fromkeys(x.strip().lower() for x in (work_modes or []) if x.strip()))
    if salary_min is not None and salary_min < 0:
        raise ValueError("Minimum salary cannot be negative")
    if result_limit is not None and result_limit < 1:
        raise ValueError("Result limit must be positive")
    where = " OR ".join('"' + x.replace('"', '') + '"' for x in locations) if locations else ""
    if len(locations) > 1:
        where = f"({where})"
    tasks = []
    # Give every role open-web coverage before spending the remaining budget.
    for source, domain in [("open_web", None), *SITES.items()]:
        for role in roles:
            restriction = f"site:{domain}" if domain else "careers"
            # Multiple selected types/modes are alternatives, not simultaneous requirements.
            def alternatives(values):
                quoted = ['"' + value.replace('"', '') + '"' for value in values]
                return "(" + " OR ".join(quoted) + ")" if len(quoted) > 1 else " ".join(quoted)
            filters = " ".join(filter(None, (alternatives(employment_types), alternatives(work_modes))))
            query = f'"{role.replace(chr(34), "")}" {where} {filters} {restriction} jobs apply'.strip()
            tasks.append({"id": f"q{len(tasks)+1:03}", "source": source,
                          "query": query, "role": role, "time_window_days": days,
                          "expected": "individual job listing"})
    total_possible = len(tasks) + int(include_ipo)
    tasks = tasks[:max_tasks - int(include_ipo)] if include_ipo and max_tasks > 1 else tasks[:max_tasks]
    if include_ipo and max_tasks > 1:
        tasks.append({"id": f"q{len(tasks)+1:03}", "source": "ipoplatform",
                      "role": "", "query": "site:ipoplatform.com/ipo/ upcoming recent India company",
                      "time_window_days": 31, "expected": "company leads only; search each company careers separately"})
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
            "roles": roles, "locations": locations, "days": days, "profile": profile,
            "freshness_tiers_days": [0, 1, 7, 30], "employment_types": employment_types,
            "work_modes": work_modes, "salary_min": salary_min, "result_limit": result_limit,
            "research_limits": {"companies_per_platform": 100, "positive_companies_per_platform": 20},
            "tasks": tasks, "total_possible_tasks": total_possible}
