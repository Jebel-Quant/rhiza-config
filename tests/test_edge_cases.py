"""Remaining branch coverage: _rhiza_yaml, status, tree, uninstall, init_scaffold."""

from __future__ import annotations

from pathlib import Path

import _rhiza_yaml
import init_scaffold
import pytest
import status
import tree
import uninstall


# --------------------------------------------------------------------------- #
# _rhiza_yaml
# --------------------------------------------------------------------------- #
def test_scalar_variants():
    assert _rhiza_yaml._scalar("") is None  # empty → None
    assert _rhiza_yaml._scalar('"q"') == "q"
    assert _rhiza_yaml._scalar("[a, b]") == ["a", "b"]
    assert _rhiza_yaml._scalar("null") is None
    assert _rhiza_yaml._scalar("true") is True
    assert _rhiza_yaml._scalar("42") == 42
    assert _rhiza_yaml._scalar("bare") == "bare"


def test_parse_subset_skips_line_without_colon():
    d = _rhiza_yaml._parse_subset("key: v\nlineWithoutColon\n")
    assert d == {"key": "v"}


def test_load_yaml_with_pyyaml(tmp_path, monkeypatch):
    class FakeYaml:
        @staticmethod
        def safe_load(text):
            if "none" in text:
                return None
            if "list" in text:
                return [1, 2]
            return {"a": 1}

    monkeypatch.setattr(_rhiza_yaml, "_pyyaml", FakeYaml)
    f = tmp_path / "f.yml"
    f.write_text("dict")
    assert _rhiza_yaml.load_yaml(f) == {"a": 1}
    f.write_text("none")
    assert _rhiza_yaml.load_yaml(f) == {}
    f.write_text("list")
    with pytest.raises(ValueError):
        _rhiza_yaml.load_yaml(f)


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #
def _lock(root, body):
    (root / ".rhiza").mkdir(parents=True, exist_ok=True)
    (root / ".rhiza" / "template.lock").write_text(body)


def test_status_human_readable_templates(tmp_path, capsys):
    _lock(
        tmp_path,
        "host: github\nrepo: a/b\nref: main\nsha: abcdef1234567890\n"
        "synced_at: 2026-07-01\nstrategy: merge\ntemplates:\n  - legal\n",
    )
    rc = status.status(tmp_path, json_output=False)
    out = capsys.readouterr().out
    assert rc == 0
    assert "Repository : github/a/b" in out
    assert "SHA        : abcdef123456" in out
    assert "Templates  : legal" in out


def test_status_human_readable_include_and_unknown_sha(tmp_path, capsys):
    _lock(tmp_path, "repo: a/b\ninclude:\n  - .github\n")  # no sha → (unknown)
    status.status(tmp_path, json_output=False)
    out = capsys.readouterr().out
    assert "SHA        : (unknown)" in out
    assert "Include    : .github" in out


def test_status_unreadable_lock(tmp_path, monkeypatch, capsys):
    _lock(tmp_path, "x: 1\n")
    monkeypatch.setattr(status, "load_yaml", lambda p: (_ for _ in ()).throw(ValueError("bad")))
    rc = status.status(tmp_path)
    assert rc == 1
    assert "Could not read" in capsys.readouterr().err


def test_status_main(tmp_path):
    _lock(tmp_path, "repo: a/b\nref: main\n")
    assert status.main([str(tmp_path), "--json"]) == 0


# --------------------------------------------------------------------------- #
# tree
# --------------------------------------------------------------------------- #
def test_tree_unreadable_lock(tmp_path, monkeypatch, capsys):
    _lock(tmp_path, "files:\n  - a\n")
    monkeypatch.setattr(tree, "load_yaml", lambda p: (_ for _ in ()).throw(ValueError("bad")))
    rc = tree.tree(tmp_path)
    assert rc == 1
    assert "Could not read" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# uninstall — the OS-error defensive branches
# --------------------------------------------------------------------------- #
def test_remove_files_permission_then_success(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("x")
    real_unlink = Path.unlink
    state = {"raised": False}

    def fake_unlink(self, *a, **k):
        if self.name == "a.txt" and not state["raised"]:
            state["raised"] = True
            raise PermissionError("read-only")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", fake_unlink)
    removed, skipped, errors = uninstall._remove_files([Path("a.txt")], tmp_path)
    assert (removed, errors) == (1, 0)  # chmod + retry succeeded


def test_remove_files_permission_then_oserror(tmp_path, monkeypatch):
    (tmp_path / "b.txt").write_text("x")
    seq = iter([PermissionError("ro"), OSError("io")])

    def fake_unlink(self, *a, **k):
        if self.name == "b.txt":
            raise next(seq)

    monkeypatch.setattr(Path, "unlink", fake_unlink)
    removed, skipped, errors = uninstall._remove_files([Path("b.txt")], tmp_path)
    assert (removed, errors) == (0, 1)  # retry raised OSError


def test_remove_files_hard_oserror(tmp_path):
    (tmp_path / "d").mkdir()  # a dir where a file is expected → IsADirectoryError (OSError)
    removed, skipped, errors = uninstall._remove_files([Path("d")], tmp_path)
    assert errors == 1


def test_remove_files_direct_oserror(tmp_path, monkeypatch):
    (tmp_path / "c.txt").write_text("x")

    def fake_unlink(self, *a, **k):
        if self.name == "c.txt":
            raise OSError("disk full")  # not PermissionError → outer OSError branch

    monkeypatch.setattr(Path, "unlink", fake_unlink)
    removed, skipped, errors = uninstall._remove_files([Path("c.txt")], tmp_path)
    assert (removed, errors) == (0, 1)


def test_remove_files_skips_absent(tmp_path):
    removed, skipped, errors = uninstall._remove_files([Path("ghost.txt")], tmp_path)
    assert (removed, skipped, errors) == (0, 1, 0)


def test_cleanup_stops_at_nonempty_dir(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "keep.txt").write_text("x")
    assert uninstall._cleanup_empty_directories([Path("pkg/gone.txt")], tmp_path) == 0


def test_cleanup_handles_oserror(tmp_path, monkeypatch):
    (tmp_path / "empty").mkdir()
    monkeypatch.setattr(Path, "rmdir", lambda self, *a, **k: (_ for _ in ()).throw(OSError("x")))
    assert uninstall._cleanup_empty_directories([Path("empty/f.txt")], tmp_path) == 0


def test_cleanup_removes_empty(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    n = uninstall._cleanup_empty_directories([Path("a/b/f.txt")], tmp_path)
    assert n == 2  # b then a removed


def test_uninstall_reports_delete_errors(tmp_path):
    _lock(tmp_path, "files:\n  - somedir\n")
    (tmp_path / "somedir").mkdir()  # listed as a file but is a dir → delete error
    assert uninstall.uninstall(tmp_path, force=True) == 1


def test_uninstall_lock_unlink_oserror(tmp_path, monkeypatch):
    _lock(tmp_path, "files:\n  - a.txt\n")
    (tmp_path / "a.txt").write_text("x")
    real_unlink = Path.unlink

    def fake_unlink(self, *a, **k):
        if self.name == "template.lock":
            raise OSError("locked")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", fake_unlink)
    assert uninstall.uninstall(tmp_path, force=True) == 1


# --------------------------------------------------------------------------- #
# init_scaffold — _run_uv_lock, _parse_components, main() text output
# --------------------------------------------------------------------------- #
def test_run_uv_lock_early_return_when_present(tmp_path):
    (tmp_path / "uv.lock").write_text("x")
    notes: list[str] = []
    init_scaffold._run_uv_lock(tmp_path, notes)
    assert notes == []


def test_run_uv_lock_uv_missing(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(init_scaffold.subprocess, "run", boom)
    notes: list[str] = []
    init_scaffold._run_uv_lock(tmp_path, notes)
    assert any("uv not found" in n for n in notes)


def test_run_uv_lock_success_and_failure(tmp_path, monkeypatch):
    class OK:
        returncode = 0

    monkeypatch.setattr(init_scaffold.subprocess, "run", lambda *a, **k: OK())
    notes: list[str] = []
    init_scaffold._run_uv_lock(tmp_path, notes)
    assert any("uv.lock" in n for n in notes)

    class Fail:
        returncode = 1
        stderr = "boom"

    monkeypatch.setattr(init_scaffold.subprocess, "run", lambda *a, **k: Fail())
    notes2: list[str] = []
    init_scaffold._run_uv_lock(tmp_path, notes2)  # no uv.lock created (mocked) → runs
    assert any("failed" in n for n in notes2)


def test_parse_components_rejects_unknown():
    with pytest.raises(ValueError):
        init_scaffold._parse_components("bogus", "python")


def test_main_text_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(init_scaffold, "_run_uv_lock", lambda t, n: None)
    rc = init_scaffold.main([str(tmp_path), "--project-name", "x", "--components", "readme"])
    assert rc == 0
    cap = capsys.readouterr()
    assert "created" in cap.out


def test_main_text_output_with_note(tmp_path, monkeypatch, capsys):
    # a Go project emits a `go mod init` note → covers the notes loop
    monkeypatch.setattr(init_scaffold, "_run_uv_lock", lambda t, n: None)
    rc = init_scaffold.main([str(tmp_path), "--language", "go", "--components", "readme"])
    assert rc == 0
    assert "note" in capsys.readouterr().err


def test_main_nothing_to_create(tmp_path, monkeypatch, capsys):
    # pre-create the always-written files so nothing new is produced
    (tmp_path / ".rhiza").mkdir()
    (tmp_path / ".rhiza" / "template.yml").write_text("x\n")
    (tmp_path / "Makefile").write_text("x\n")
    monkeypatch.setattr(init_scaffold, "_run_uv_lock", lambda t, n: None)
    rc = init_scaffold.main([str(tmp_path), "--project-name", "x", "--components", ""])
    assert rc == 0
    assert "nothing to create" in capsys.readouterr().err
