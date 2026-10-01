"""Synthetic-only regression tests for fresh intake and data boundaries."""
import io
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from job_agent import privacy
from job_agent.cli import main
from job_agent.plan import make_plan
from job_agent.ranking import rank
from job_agent.records import normalize
from job_agent.reporting import write_reports


def listing(index=0, dated=True):
    return normalize({
        "task_id": "q001", "title": "Data Analyst job", "company": "Example",
        "snippet": "Python SQL analytics in India", "location": "India",
        "result_url": f"https://jobs.lever.co/example/{index}",
        "posting_date": datetime.now(timezone.utc).date().isoformat() if dated else None,
        "posting_date_source": "platform_label" if dated else "unknown",
    }, {"q001"})


def test_prepare_and_import_are_fresh_and_profile_free(tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(privacy, "PROJECT_ROOT", project)
    resume = tmp_path / "original.txt"
    private_text = "PRIVATE-CANDIDATE private@example.invalid Python SQL Data Analyst with 2 years of experience"
    resume.write_text(private_text)
    output = tmp_path / "chosen-results"
    args = ["prepare", "--resume", str(resume), "--output-dir", str(output), "--roles", "Data Analyst",
            "--location", "India", "--employment-type", "full-time", "--work-mode", "any",
            "--relocate", "yes", "--days", "30", "--result-limit", "75"]
    assert main(args) == 0
    printed = capsys.readouterr().out
    plan = json.loads(printed)
    assert "profile" not in plan and "PRIVATE-CANDIDATE" not in printed
    assert plan["result_limit"] == 75 and plan["willing_to_relocate"]
    assert not output.exists() and not list(project.iterdir())
    envelope = {"plan": plan, "results": {"schema_version": 1, "results": [listing()]}}
    for _ in range(2):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(envelope)))
        assert main(["import", "--resume", str(resume), "--output-dir", str(output)]) == 0
    reports = list(output.glob("*/report.json"))
    assert len(reports) == 2
    for report in reports:
        data = json.loads(report.read_text())
        assert len(data["opportunities"]) == 1
        assert not data["target_met"]
        assert data["requested_result_count"] == 75
    for artifact in output.rglob("*"):
        if artifact.is_file():
            text = artifact.read_text(encoding="utf-8-sig")
            for marker in ("PRIVATE-CANDIDATE", "private@example.invalid", "resume_sha256",
                           "resume_excerpt", '"candidate"', '"profile"', "experience_entries"):
                assert marker not in text
    assert resume.read_text() == private_text
    assert not list(project.iterdir())
    assert not list(tmp_path.rglob("*.sqlite"))


def test_interactive_default_run_asks_fresh_questions_twice(tmp_path, monkeypatch, capsys):
    resume = tmp_path / "original.txt"
    resume.write_text("Synthetic Data Analyst with Python SQL and 2 years of experience")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    answers = [str(resume), str(tmp_path / "reports"), "Data Analyst", "",
               "India", "", "no", "", "", ""]
    for _ in range(2):
        iterator = iter(answers)
        monkeypatch.setattr("builtins.input", lambda: next(iterator))
        assert main([]) == 0
        captured = capsys.readouterr()
        plan = json.loads(captured.out)
        assert plan["result_limit"] == 20
        for prompt in ("Resume path", "External folder", "Target roles", "Target locations",
                       "Employment types", "Work modes", "relocate", "salary", "results wanted"):
            assert prompt in captured.err
    assert not (tmp_path / "reports").exists()


def test_noninteractive_does_not_reuse_defaults(capsys):
    assert main(["prepare"]) == 2
    assert "questionnaire" in capsys.readouterr().err


def test_project_paths_and_traversal_are_rejected(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(privacy, "PROJECT_ROOT", project)
    for path in (project, project / "reports", project / "../project/nested"):
        with pytest.raises(ValueError, match="outside"):
            privacy.output_directory(path)
    assert privacy.output_directory(tmp_path / "project-other") == tmp_path / "project-other"
    with pytest.raises(ValueError):
        write_reports(str(project / "reports"), {}, [], [], [], [])


def test_symlink_into_project_is_rejected(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(privacy, "PROJECT_ROOT", project)
    link = tmp_path / "outside-link"
    try:
        link.symlink_to(project, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("OS does not permit symlinks for this user")
        # Windows directory junctions need no symbolic-link privilege.
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "New-Item -ItemType Junction -Path '" + str(link).replace("'", "''")
                        + "' -Target '" + str(project).replace("'", "''") + "' | Out-Null"],
                       check=True, capture_output=True)
    with pytest.raises(ValueError):
        privacy.output_directory(link / "reports")
    # Remove only the link, never its target tree.
    if os.name == "nt":
        os.rmdir(link)
    else:
        link.unlink()


def test_internal_resume_is_rejected(tmp_path, monkeypatch):
    from job_agent.cli import candidate_from
    monkeypatch.setattr(privacy, "PROJECT_ROOT", tmp_path)
    path = tmp_path / "resume.txt"
    path.write_text("Synthetic private Data Analyst resume with Python and SQL.")
    with pytest.raises(ValueError, match="outside"):
        candidate_from(path)


def test_freshness_window_does_not_count_older_jobs():
    from datetime import timedelta
    plan = make_plan({}, ["Data Analyst"], ["India"], days=1)
    job = listing()
    job["posting_date"] = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()
    assert rank([job], plan)[0] == []


@pytest.mark.parametrize("bad_kind", ["profile", "destination", "listing"])
def test_invalid_import_writes_nothing(tmp_path, monkeypatch, bad_kind):
    output = tmp_path / "reports"
    resume = tmp_path / "original.txt"
    resume.write_text("Synthetic Data Analyst with Python SQL experience")
    plan = make_plan({}, ["Data Analyst"], ["India"])
    plan.pop("profile")
    plan["output_dir"] = str(output)
    batch = {"schema_version": 1, "results": [listing()]}
    if bad_kind == "profile":
        plan["profile"] = {"resume_excerpt": "PRIVATE"}
    elif bad_kind == "destination":
        plan["output_dir"] = str(tmp_path / "different")
    else:
        batch["results"].append({"bad": True})
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"plan": plan, "results": batch})))
    assert main(["import", "--resume", str(resume), "--output-dir", str(output)]) == 2
    assert not output.exists()


def test_report_whitelist_omits_candidate_fields(tmp_path):
    plan = make_plan({"resume_excerpt": "PRIVATE-TEXT", "skills": ["PRIVATE-SKILL"]},
                     ["Data Analyst"], ["India"])
    plan["private_note"] = "PRIVATE-NOTE"
    job = listing()
    job.update({"fit_explanation": "PRIVATE-FIT", "candidate": "PRIVATE-CANDIDATE",
                "matched_resume_skills_in_snippet": ["PRIVATE-SKILL"]})
    folder = write_reports(tmp_path / "reports", plan, [job], [], [], [])
    assert all("PRIVATE" not in p.read_text(encoding="utf-8-sig") for p in folder.iterdir())


def test_requested_count_above_fifty_and_unknown_dates_separate(tmp_path):
    plan = make_plan({}, ["Data Analyst"], ["India"], result_limit=75)
    jobs = [listing(i) for i in range(90)] + [listing(100, dated=False)]
    ranked, leads = rank(jobs, plan)
    assert len(ranked) == 76
    folder = write_reports(tmp_path / "reports", plan, ranked, leads, [])
    report = json.loads((folder / "report.json").read_text())
    assert report["qualifying_result_count"] == 75 and report["target_met"]
    assert len(report["date_unknown"]) == 1
    assert "Date unknown" in (folder / "report.html").read_text()


def test_source_allowlist_ignores_private_artifacts(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    root = Path(__file__).resolve().parents[1]
    (tmp_path / ".gitignore").write_text((root / ".gitignore").read_text())
    paths = ["resume.pdf", "personal.txt", "someone/resume.docx", "data/history.sqlite",
             "report.html", "results.json", "plan.json", ".env", "backup.zip",
             "job_agent/private.json", "tests/private.csv", "notes.md"]
    process = subprocess.run(["git", "-C", str(tmp_path), "check-ignore", "--stdin", "-z"],
                             input="\0".join(paths).encode(), capture_output=True, check=True)
    assert set(process.stdout.decode().strip("\0").split("\0")) == set(paths)
    for name in ("README.md", "AGENTS.md", "main.py", "job_agent/cli.py", "tests/test_privacy.py"):
        check = subprocess.run(["git", "-C", str(tmp_path), "check-ignore", name], capture_output=True)
        assert check.returncode == 1, name
