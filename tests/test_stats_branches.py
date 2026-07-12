"""Branch/error-path coverage for `scripts/stats.py` (complements test_stats.py)."""

from __future__ import annotations

import json

import stats


def make_out(mapping):
    keys = sorted(mapping, key=len, reverse=True)

    def _out(cmd, timeout=60):
        joined = " ".join(cmd)
        for k in keys:
            if k in joined:
                return mapping[k]
        return None

    return _out


# --- shell helpers (real subprocess) ---------------------------------------
def test_run_out_have_tool(monkeypatch):
    assert stats.run(["python3", "-c", "print('hi')"]).returncode == 0
    assert stats.run(["definitely-not-a-binary-xyz-123"]) is None
    assert stats.out(["python3", "-c", "print('hi')"]) == "hi"
    assert stats.out(["python3", "-c", "import sys; sys.exit(1)"]) is None  # nonzero → None
    assert stats.have("python3") is True
    assert stats.have("definitely-not-a-binary-xyz-123") is False

    monkeypatch.setattr(stats, "have", lambda b: b == "radon")
    assert stats.tool("radon") == ["radon"]
    monkeypatch.setattr(stats, "have", lambda b: b == "uvx")
    monkeypatch.setattr(stats, "SLOW", True)
    assert stats.tool("radon") == ["uvx", "radon"]
    monkeypatch.setattr(stats, "SLOW", False)
    assert stats.tool("radon") is None


def test_default_branch_symbolic_ref_fallback(monkeypatch):
    monkeypatch.setattr(
        stats, "out", make_out({"symbolic-ref": "refs/remotes/origin/develop"})
    )  # gh returns None, symbolic-ref hit
    assert stats.default_branch() == "develop"


# --- identity: gh json parse failure + gitlab branch -----------------------
def test_identity_gh_json_parse_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(
        stats,
        "out",
        make_out(
            {
                "remote get-url origin": "https://github.com/a/b",
                "stargazerCount,forkCount": "{not json",
            }
        ),
    )
    s, ctx = stats.section_identity(tmp_path, None)
    assert any("gh json parse failed" in str(v) for _, v in s.rows)


def test_identity_gitlab(tmp_path, monkeypatch):
    monkeypatch.setattr(
        stats,
        "out",
        make_out(
            {
                "remote get-url origin": "https://gitlab.com/grp/proj",
                "projects/:id": json.dumps({"stars": 4, "forks": 1}),
            }
        ),
    )
    s, ctx = stats.section_identity(tmp_path, None)
    assert ctx["stars"] == 4
    # bad json → parse-fail branch
    monkeypatch.setattr(
        stats,
        "out",
        make_out({"remote get-url origin": "https://gitlab.com/g/p", "projects/:id": "{bad"}),
    )
    s2, _ = stats.section_identity(tmp_path, None)
    assert any("glab json parse failed" in str(v) for _, v in s2.rows)


# --- code size: language split row + unreadable src file -------------------
def test_code_size_split_and_unreadable(tmp_path, monkeypatch):
    files = {None: ["src/ghost.py"], "src": ["src/ghost.py"], "tests": [], "docs": []}
    monkeypatch.setattr(stats, "ls_files", lambda ps=None: files.get(ps, []))
    monkeypatch.setattr(stats, "have", lambda b: False)
    monkeypatch.setattr(
        stats, "language_split", lambda scope: {"code": 10, "comment": 2, "blank": 1, "tool": "scc"}
    )
    monkeypatch.setattr(stats, "out", lambda cmd, timeout=60: None)
    s, ctx = stats.section_code_size(tmp_path, None)  # src/ghost.py doesn't exist → read OSError
    rows = dict(s.rows)
    assert "scc" in rows["Code / comment / blank"]


def test_language_split_parse_errors(monkeypatch):
    monkeypatch.setattr(stats, "have", lambda b: b == "scc")
    monkeypatch.setattr(stats, "out", make_out({"scc --format json": "{bad"}))
    assert stats.language_split(None) is None
    monkeypatch.setattr(stats, "have", lambda b: b == "tokei")
    monkeypatch.setattr(stats, "out", make_out({"tokei --output json": "{bad"}))
    assert stats.language_split(None) is None


# --- tests section: interrogate present ------------------------------------
def test_tests_interrogate(tmp_path, monkeypatch):
    monkeypatch.setattr(stats, "ls_files", lambda ps=None: ["src/m.py"] if ps in ("src",) else [])
    monkeypatch.setattr(
        stats, "tool", lambda name: ["interrogate"] if name == "interrogate" else None
    )
    monkeypatch.setattr(stats, "out", make_out({"interrogate": "actual: 95.5%"}))
    s = stats.section_tests(tmp_path)
    assert any("95.5%" in str(v) for _, v in s.rows)


# --- complexity: no radon / cc failed --------------------------------------
def test_complexity_no_radon(monkeypatch):
    monkeypatch.setattr(stats, "ls_files", lambda ps=None: ["src/m.py"] if ps == "src" else [])
    monkeypatch.setattr(stats, "tool", lambda name: None)
    s = stats.section_complexity()
    assert any("radon not on PATH" in str(v) for _, v in s.rows)


def test_complexity_cc_failed(monkeypatch):
    monkeypatch.setattr(stats, "ls_files", lambda ps=None: ["src/m.py"] if ps == "src" else [])
    monkeypatch.setattr(stats, "tool", lambda name: ["radon"])
    monkeypatch.setattr(stats, "out", lambda cmd, timeout=60: None)  # cc → None
    s = stats.section_complexity()
    assert any("radon cc failed" in str(v) for _, v in s.rows)


# --- deps: requirements.txt + SLOW outdated --------------------------------
def test_deps_requirements_and_outdated(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["a"]\n')
    (tmp_path / "requirements.txt").write_text("# comment\nflask\nrequests\n")
    monkeypatch.setattr(stats, "have", lambda b: True)
    monkeypatch.setattr(stats, "SLOW", True)
    monkeypatch.setattr(
        stats, "out", make_out({"pip list --outdated": "Package Version\n---- ---\nflask 1 2"})
    )
    s = stats.section_deps(tmp_path)
    rows = dict(s.rows)
    assert "requirements.txt" in rows["Pinned packages"]
    assert rows["Outdated deps"] == 1


# --- git: bad date, release parse fail, issues ValueError ------------------
def test_git_edge_branches(monkeypatch):
    ctx = {"platform": "GitHub", "slug": "a/b", "default_branch": "main"}
    mapping = {
        "rev-list --count HEAD": "5",
        "log --format=%as": "not-a-date\nalso-bad",
        "release list": "{bad json",
        "pr list": "2",
        "open_issues_count": "notanumber",
        "run list": "success",
    }
    monkeypatch.setattr(stats, "out", make_out(mapping))
    s, gc = stats.section_git(ctx)
    rows = dict(s.rows)
    assert "First commit" in rows  # date parse failed → First commit row
    assert rows["Open issues"] == "notanumber"  # int() failed → raw oic


# --- rhiza: status json decode error + no profiles -------------------------
def test_rhiza_status_decode_error_and_no_profiles(tmp_path, monkeypatch):
    rhiza = tmp_path / ".rhiza"
    rhiza.mkdir()
    (rhiza / "template.yml").write_text('ref: "v1.0.0"\ntemplates:\n  - core\n')  # no profiles key
    monkeypatch.setattr(stats, "out", make_out({"rhiza status": "not json at all"}))
    s, rc = stats.section_rhiza(tmp_path)
    rows = dict(s.rows)
    assert "no profiles" in rows["Active profiles"]


def test_identity_host_unavailable(tmp_path, monkeypatch):
    # GitHub remote but `gh repo view` yields nothing → "gh unavailable" else branch
    monkeypatch.setattr(stats, "out", make_out({"remote get-url origin": "https://github.com/a/b"}))
    s, _ = stats.section_identity(tmp_path, None)
    assert any("gh unavailable" in str(v) for _, v in s.rows)
    # GitLab remote but `glab api` yields nothing → "glab unavailable" else branch
    monkeypatch.setattr(stats, "out", make_out({"remote get-url origin": "https://gitlab.com/a/b"}))
    s2, _ = stats.section_identity(tmp_path, None)
    assert any("glab unavailable" in str(v) for _, v in s2.rows)


def test_tests_unreadable_test_file(tmp_path, monkeypatch):
    # ls_files reports a test file that isn't on disk → read_text OSError → skipped
    monkeypatch.setattr(
        stats, "ls_files", lambda ps=None: ["tests/test_ghost.py"] if ps == "tests" else []
    )
    monkeypatch.setattr(stats, "tool", lambda name: None)
    s = stats.section_tests(tmp_path)
    assert any("0 test functions" in str(v) for _, v in s.rows)


def test_git_release_empty_and_issues_without_prs(monkeypatch):
    ctx = {"platform": "GitHub", "slug": "a/b", "default_branch": "main"}
    mapping = {
        "rev-list --count HEAD": "5",
        "release list": "[]",  # empty → "none"
        "open_issues_count": "9",  # present, but no "pr list" key → prs None → elif branch
    }
    monkeypatch.setattr(stats, "out", make_out(mapping))
    s, gc = stats.section_git(ctx)
    rows = dict(s.rows)
    assert rows["Latest release"] == "none"
    assert "incl. PRs" in rows["Open issues"]


def test_rhiza_status_json_returns_non_object(tmp_path, monkeypatch):
    rhiza = tmp_path / ".rhiza"
    rhiza.mkdir()
    (rhiza / "template.yml").write_text('ref: "v1.0.0"\nprofiles: [github-project]\n')
    # valid JSON but a list, not a dict → _rhiza_status_json returns None
    monkeypatch.setattr(stats, "out", make_out({"rhiza status": "[1, 2, 3]"}))
    s, rc = stats.section_rhiza(tmp_path)
    assert rc["ref"] == "v1.0.0"
