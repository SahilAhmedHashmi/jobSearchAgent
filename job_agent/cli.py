"""Stateless searches: runtime profiles, external reports, no history."""
import argparse
import json
import sys
from datetime import datetime, timezone

from .plan import make_plan
from .privacy import external_path, output_directory
from .ranking import rank
from .records import validate_batch
from .reporting import write_reports
from .resume import profile, read_resume


def ask(prompt):
    print(prompt, end=" ", file=sys.stderr, flush=True)
    return input().strip()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Fresh job search; no project data storage")
    sub = parser.add_subparsers(dest="command")
    prep = sub.add_parser("prepare", help="Print a resume-free plan; write no files")
    for name in ("resume", "output-dir", "roles", "relocate"):
        prep.add_argument("--" + name)
    for name in ("location", "employment-type", "work-mode"):
        prep.add_argument("--" + name, action="append")
    prep.add_argument("--days", type=int)
    prep.add_argument("--max-tasks", type=int, default=160)
    prep.add_argument("--no-ipo", action="store_true")
    prep.add_argument("--salary-min", type=float)
    prep.add_argument("--result-limit", type=int)
    imp = sub.add_parser("import", help="Read {plan, results} JSON from stdin; export external reports")
    imp.add_argument("--resume", required=True)
    imp.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    return parser.parse_args(["prepare"]) if args.command is None else args


def candidate_from(path):
    text, digest = read_resume(str(external_path(path)))
    return profile(text, digest)


def prepare(args):
    interactive = sys.stdin.isatty()
    if not interactive and (not args.resume or not args.output_dir or not args.roles or
                            not args.location or not args.employment_type or not args.work_mode or
                            args.relocate is None or args.result_limit is None or args.days is None):
        raise ValueError("Complete the fresh-run questionnaire first: provide --resume, --output-dir, --roles, "
                         "--location, --employment-type, --work-mode (or any), --relocate, --days and --result-limit")
    resume = args.resume or ask("Resume path outside the project (TXT, PDF or DOCX):")
    candidate = candidate_from(resume)
    destination = output_directory(args.output_dir or ask("External folder for this run's results:"))
    if not args.roles:
        print("Suggested roles: " + ", ".join(candidate["role_suggestions"]), file=sys.stderr)
    roles = (args.roles or ask("Target roles, comma-separated:")).split(",")
    employment = args.employment_type or (ask("Employment types (default full-time):") or "full-time").split(",")
    locations = args.location or ask("Target locations, comma-separated:").split(",")
    modes = args.work_mode or (ask("Work modes: remote, hybrid, on-site, any (default any):") or "any").split(",")
    relocate = args.relocate or ask("Willing to relocate? yes/no:").lower()
    if relocate not in ("yes", "no"):
        raise ValueError("Relocation answer must be yes or no")
    salary = args.salary_min
    if interactive and salary is None:
        answer = ask("Minimum annual salary in INR (optional, blank for none):")
        salary = float(answer) if answer else None
    count = args.result_limit if args.result_limit is not None else int(ask("Qualifying results wanted (default 20; larger counts welcome):") or "20")
    days = args.days if args.days is not None else 30
    if interactive and args.days is None:
        print("Freshness rule: last 30 days, newest postings first; hourly tiers require timestamp evidence.", file=sys.stderr)
    if not any(x.strip() for x in locations):
        raise ValueError("Specify at least one target location")
    plan = make_plan({}, roles, locations, days, not args.no_ipo, args.max_tasks,
                     employment_types=employment, work_modes=[m for m in modes if m.strip().lower() != "any"],
                     salary_min=salary, result_limit=count)
    plan.pop("profile", None)
    plan["willing_to_relocate"] = relocate == "yes"
    plan["output_dir"] = str(destination)
    print(json.dumps(plan, indent=2, ensure_ascii=False))


def import_results(args):
    destination = output_directory(args.output_dir)
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict) or not isinstance(payload.get("plan"), dict):
        raise ValueError("stdin must contain an object with plan and results")
    plan = payload["plan"]
    if (plan.get("schema_version") != 1 or not isinstance(plan.get("tasks"), list) or
            not isinstance(plan.get("roles"), list) or not plan["roles"] or
            not all(isinstance(r, str) and r.strip() for r in plan["roles"]) or
            not isinstance(plan.get("days"), int) or not 1 <= plan["days"] <= 31 or
            not all(isinstance(t, dict) and isinstance(t.get("id"), str) for t in plan["tasks"]) or
            not isinstance(plan.get("result_limit"), int) or plan["result_limit"] < 1):
        raise ValueError("Invalid search plan")
    if any(k in plan for k in ("profile", "candidate", "resume_excerpt", "resume_sha256", "previous_job_ids", "applied_job_ids")):
        raise ValueError("Use a fresh resume-free plan; stored profiles and history are not supported")
    if not plan.get("output_dir") or output_directory(plan["output_dir"]) != destination:
        raise ValueError("Output folder must match the folder selected at the start of this run")
    found, errors, health = validate_batch(payload.get("results"), plan)
    if errors:
        for error in errors:
            print(f"Rejected: {error}", file=sys.stderr)
        raise ValueError("Fix rejected results before exporting; no reports written")
    runtime_plan = {**plan, "profile": candidate_from(args.resume)}
    matches, leads = rank(found, runtime_plan)
    folder = destination / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = write_reports(str(folder), runtime_plan, matches, leads, errors, health)
    dated = sum(j["posting_date"] is not None and j.get("salary_status") != "unverified" for j in matches)
    undated = sum(j["posting_date"] is None for j in matches)
    unverified = sum(j["posting_date"] is not None and j.get("salary_status") == "unverified" for j in matches)
    if plan.get("include_salary_unverified"):
        print(f"{dated + unverified}/{plan['result_limit']} dated results including {unverified} salary-unverified listings accepted for this run")
        print(f"{dated} salary-verified or unrestricted jobs, {undated} undated jobs, {len(leads)} company leads")
    else:
        print(f"{dated}/{plan['result_limit']} dated qualifying jobs, {undated} undated jobs, {unverified} dated salary-unverified jobs, {len(leads)} company leads")
    print(f"Reports: {out / 'report.html'}, {out / 'report.csv'}, {out / 'report.json'}")


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.command == "prepare":
            prepare(args)
        else:
            import_results(args)
        return 0
    except (ValueError, OSError, EOFError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
