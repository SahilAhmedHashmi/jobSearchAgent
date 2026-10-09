"""Validation and honest interpretation of agent-collected search results."""
import hashlib
import ipaddress
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid", "gclid"}
JOB_HOSTS = ("myworkdayjobs.com", "workdayjobs.com", "greenhouse.io", "lever.co",
             "ashbyhq.com", "workable.com", "smartrecruiters.com", "icims.com",
             "jobvite.com", "linkedin.com", "indeed.com", "naukri.com", "foundit.in", "wellfound.com",
             "bayt.com", "naukrigulf.com", "gulftalent.com", "gulfjobs.com",
             "founditgulf.com", "qatarliving.com", "dubizzle.com")
JOB_TERMS = re.compile(r"\b(job|jobs|career|careers|vacancy|opening|position|apply|requisition)\b", re.I)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def clean_url(url: str) -> str:
    if not isinstance(url, str) or len(url) > 4000:
        raise ValueError("Invalid URL")
    p = urlsplit(url)
    host = (p.hostname or "").lower().rstrip(".")
    if p.scheme not in ("https", "http") or not host or p.username or p.password or p.port not in (None, 80, 443):
        raise ValueError("Only ordinary public HTTP(S) URLs are supported")
    if host in ("localhost",) or host.endswith((".local", ".internal")):
        raise ValueError("Private hostname")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise ValueError("Private address")
    except ValueError as exc:
        if "Private address" in str(exc):
            raise
    params = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in TRACKING]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", urlencode(params), ""))


def _date(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise ValueError("Date must be YYYY-MM-DD or null")
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def normalize(item: dict, task_ids: set[str]) -> dict:
    if not isinstance(item, dict) or not isinstance(item.get("task_id"), str) or item.get("task_id") not in task_ids:
        raise ValueError("Result must reference an existing task_id")
    url = clean_url(item.get("result_url", ""))
    title = str(item.get("title") or "").strip()[:220]
    snippet = str(item.get("snippet") or "").strip()
    if not title or not snippet:
        raise ValueError("Search title and snippet are required")
    kind = item.get("kind", "job")
    if kind not in ("job", "company_lead"):
        raise ValueError("kind must be job or company_lead")
    host = urlsplit(url).hostname
    if kind == "job" and (host == "ipoplatform.com" or host.endswith(".ipoplatform.com")):
        raise ValueError("IPO pages are company leads, not jobs")
    if kind == "company_lead" and not item.get("company"):
        raise ValueError("Company leads require a company name")
    if kind == "job" and not (JOB_TERMS.search(title + " " + url) or any(host == h or host.endswith('.' + h) for h in JOB_HOSTS)):
        raise ValueError("Result has no recognizable job signal")
    if kind == "job" and urlsplit(url).path.rstrip('/').lower() in ('', '/jobs', '/careers', '/jobs/search', '/jobs/results', '/search'):
        raise ValueError("Use an individual listing, not a discovery page")
    app_url = clean_url(item["application_url"]) if item.get("application_url") else None
    redirect = clean_url(item["redirect_url"]) if item.get("redirect_url") else None
    origin = item.get("application_url_source", "unknown")
    if origin not in ("search_result", "browser_observed", "unknown"):
        raise ValueError("Invalid application_url_source")
    if app_url and origin == "unknown":
        raise ValueError("Application URL requires an evidence source")
    if not app_url and origin != "unknown":
        raise ValueError("Application URL source requires an application URL")
    if app_url and origin == "search_result" and app_url != url:
        raise ValueError("search_result application URL must match the result URL")
    status = item.get("url_status", "unknown")
    checked = item.get("checked_at") or None
    if checked:
        try:
            timestamp = datetime.fromisoformat(checked.replace('Z', '+00:00'))
            if timestamp.tzinfo is None:
                raise ValueError("Timezone required")
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("checked_at must be an ISO timestamp with timezone") from exc
    if (status in ("opens", "redirects", "blocked", "closed") or redirect or origin == "browser_observed") and not checked:
        raise ValueError("Observed links and URL checks require checked_at")
    if status == "redirects" and not redirect:
        raise ValueError("redirects requires an observed redirect_url")
    page_date = _date(item.get("search_page_date"))
    posting = _date(item.get("posting_date"))
    date_source = item.get("posting_date_source", "unknown")
    if posting and date_source not in ("platform_label", "employer_page", "search_snippet"):
        raise ValueError("Posting date requires explicit source")
    if posting and posting > datetime.now(timezone.utc).date().isoformat():
        raise ValueError("Future posting date")
    posting_timestamp = item.get("posting_timestamp") or None
    if posting_timestamp:
        try:
            posted_at = datetime.fromisoformat(posting_timestamp.replace("Z", "+00:00"))
            if posted_at.tzinfo is None or not posting or posted_at.date().isoformat() != posting:
                raise ValueError("Timestamp requires timezone and matching evidenced posting date")
            if posted_at > datetime.now(timezone.utc):
                raise ValueError("Future posting timestamp")
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Invalid posting_timestamp: use an evidenced ISO timestamp with timezone and matching posting_date") from exc
    company = str(item.get("company") or "").strip()[:150]
    salary = item.get("salary")
    if salary is not None and (not isinstance(salary, (int, float)) or salary < 0):
        raise ValueError("salary must be a non-negative number or null")
    result = {
        "task_id": item["task_id"], "kind": kind, "title": title, "company": company,
        "location": str(item.get("location") or "").strip()[:150], "snippet": snippet,
        "result_url": item["result_url"], "application_url": item.get("application_url") or None, "application_url_source": origin,
        "redirect_url": item.get("redirect_url") or None, "search_page_date": page_date,
        "posting_date": posting, "posting_date_source": date_source if posting else "unknown",
        "posting_timestamp": posting_timestamp,
        "checked_at": checked,
        "url_status": status,
        "platform": str(item.get("platform") or urlsplit(url).hostname or "")[:100],
        "salary": salary, "salary_currency": str(item.get("salary_currency") or "")[:12],
        "employment_type": str(item.get("employment_type") or "").strip()[:40],
        "work_mode": str(item.get("work_mode") or "").strip()[:40],
        "experience_required_years": item.get("experience_required_years"),
        "evidence": str(item.get("evidence") or "")[:800],
    }
    if result["url_status"] not in ("not_checked", "opens", "redirects", "blocked", "closed", "unknown"):
        raise ValueError("Invalid url_status")
    identity = (kind + ':' + company.lower() + ':' if kind == 'company_lead' else '') + (redirect or app_url or url)
    result["id"] = hashlib.sha256(identity.encode()).hexdigest()[:20]
    return result


def load_batch(path: str, plan: dict) -> tuple[list[dict], list[str], list[dict]]:
    with open(path, encoding="utf-8-sig") as stream:
        payload = json.load(stream)
    return validate_batch(payload, plan)


def validate_batch(payload: dict, plan: dict) -> tuple[list[dict], list[str], list[dict]]:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("results"), list):
        raise ValueError("Expected schema_version 1 and a results array")
    task_ids = {x["id"] for x in plan["tasks"]}
    jobs, errors = [], []
    for i, raw in enumerate(payload["results"], 1):
        try:
            if isinstance(raw, dict) and raw.get("kind") == "company_lead":
                if not any(t['id'] == raw.get('task_id') and t.get('source') == 'ipoplatform' for t in plan['tasks']):
                    raise ValueError("Company leads must reference the IPO task")
            jobs.append(normalize(raw, task_ids))
        except (ValueError, TypeError) as exc:
            errors.append(f"Result {i}: {exc}")
    health = payload.get("source_health", [])
    if not isinstance(health, list):
        errors.append("source_health must be an array")
        health = []
    health = [{"source": str(x.get("source", ""))[:80],
               "status": str(x.get("status", ""))[:80],
               "note": str(x.get("note", ""))[:500]}
              for x in health if isinstance(x, dict)][:100]
    return jobs, errors, health
