"""Branch coverage for `scripts/validate.py` — every field validator + orchestration."""

from __future__ import annotations

import pytest
import validate as v


def log():
    return v.Log(verbose=True)


# --- language structure -----------------------------------------------------
def test_python_structure(tmp_path):
    lg = log()
    assert v._validate_python_structure(lg, tmp_path) is False  # no pyproject
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    lg2 = log()
    assert v._validate_python_structure(lg2, tmp_path) is True
    assert not lg2.warnings  # src + tests present → no warnings


def test_go_structure(tmp_path):
    lg = log()
    assert v._validate_go_structure(lg, tmp_path) is False  # no go.mod, warns on cmd/pkg
    (tmp_path / "go.mod").write_text("module x\n")
    (tmp_path / "cmd").mkdir()
    (tmp_path / "pkg").mkdir()
    (tmp_path / "internal").mkdir()
    lg2 = log()
    assert v._validate_go_structure(lg2, tmp_path) is True


def test_check_project_structure_unknown_language(tmp_path):
    lg = log()
    assert v._check_project_structure(lg, tmp_path, "rust") is True
    assert lg.warnings


# --- preconditions ----------------------------------------------------------
def test_check_git_repository(tmp_path):
    assert v._check_git_repository(log(), tmp_path) is False
    (tmp_path / ".git").mkdir()
    assert v._check_git_repository(log(), tmp_path) is True


def test_template_file_exists(tmp_path):
    lg = log()
    ok, path = v._check_template_file_exists(lg, tmp_path, None)
    assert ok is False and path == tmp_path / ".rhiza" / "template.yml"
    # outside the target → relative_to ValueError branch, then missing
    outside = tmp_path.parent / "elsewhere.yml"
    ok2, _ = v._check_template_file_exists(log(), tmp_path, outside)
    assert ok2 is False
    # present
    tf = tmp_path / "t.yml"
    tf.write_text("x: 1\n")
    ok3, _ = v._check_template_file_exists(log(), tmp_path, tf)
    assert ok3 is True


def test_parse_template_file(tmp_path, monkeypatch):
    tf = tmp_path / "t.yml"
    tf.write_text('repository: "a/b"\n')
    ok, cfg = v._parse_template_file(log(), tf)
    assert ok and cfg["repository"] == "a/b"

    monkeypatch.setattr(v, "load_yaml", lambda p: (_ for _ in ()).throw(ValueError("bad")))
    ok2, cfg2 = v._parse_template_file(log(), tf)
    assert ok2 is False and cfg2 is None

    monkeypatch.setattr(v, "load_yaml", lambda p: (_ for _ in ()).throw(OSError("io")))
    ok3, _ = v._parse_template_file(log(), tf)
    assert ok3 is False

    monkeypatch.setattr(v, "load_yaml", lambda p: {})
    ok4, _ = v._parse_template_file(log(), tf)
    assert ok4 is False  # empty


# --- profiles field ---------------------------------------------------------
@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({}, None),
        ({"profiles": "x"}, False),
        ({"profiles": []}, False),
        ({"profiles": [""]}, False),
        ({"profiles": ["github-project"]}, True),
    ],
)
def test_profiles_field(config, expected):
    assert v._validate_profiles_field(log(), config) is expected


# --- configuration mode -----------------------------------------------------
def test_config_mode_profiles_invalid():
    assert v._validate_configuration_mode(log(), {"profiles": "x"}) is False


def test_config_mode_bundles_renamed():
    assert v._validate_configuration_mode(log(), {"bundles": ["x"], "profiles": ["p"]}) is False


def test_config_mode_nothing_specified():
    assert v._validate_configuration_mode(log(), {"ref": "main"}) is False


def test_config_mode_variants():
    assert v._validate_configuration_mode(log(), {"profiles": ["p"]}) is True
    assert v._validate_configuration_mode(log(), {"templates": ["a"], "include": ["b"]}) is True
    assert v._validate_configuration_mode(log(), {"templates": ["a"]}) is True
    assert v._validate_configuration_mode(log(), {"include": ["b"]}) is True


# --- required fields + repo format -----------------------------------------
def test_required_fields():
    assert v._validate_required_fields(log(), {}) is False
    assert v._validate_required_fields(log(), {"repository": 5}) is False
    assert v._validate_required_fields(log(), {"repository": "a/b"}) is True
    assert v._validate_required_fields(log(), {"template-repository": "a/b"}) is True


def test_repository_format():
    assert v._validate_repository_format(log(), {}) is True  # absent → caught elsewhere
    assert v._validate_repository_format(log(), {"repository": 5}) is False
    assert v._validate_repository_format(log(), {"repository": "noslash"}) is False
    assert v._validate_repository_format(log(), {"repository": "a/b"}) is True


# --- string list ------------------------------------------------------------
def test_string_list():
    assert v._validate_string_list(log(), {}, "templates", "ex") is True  # absent
    assert v._validate_string_list(log(), {"templates": "x"}, "templates", "ex") is False
    assert v._validate_string_list(log(), {"templates": []}, "templates", "ex") is False
    lg = log()
    assert v._validate_string_list(lg, {"templates": ["a", 5]}, "templates", "ex") is True
    assert lg.warnings  # non-string entry warned


# --- optional fields --------------------------------------------------------
def test_branch_field():
    v._validate_branch_field(log(), {})  # absent → no-op
    lg = log()
    v._validate_branch_field(lg, {"ref": 5})
    assert lg.warnings
    lg2 = log()
    v._validate_branch_field(lg2, {"template-branch": "main"})
    assert not lg2.warnings


def test_host_field():
    v._validate_host_field(log(), {})  # absent
    lg = log()
    v._validate_host_field(lg, {"template-host": 5})
    assert lg.warnings
    lg2 = log()
    v._validate_host_field(lg2, {"template-host": "bitbucket"})
    assert lg2.warnings
    lg3 = log()
    v._validate_host_field(lg3, {"template-host": "github"})
    assert not lg3.warnings


def test_language_field():
    v._validate_language_field(log(), {})
    lg = log()
    v._validate_language_field(lg, {"language": 5})
    assert lg.warnings
    lg2 = log()
    v._validate_language_field(lg2, {"language": "cobol"})
    assert lg2.warnings
    lg3 = log()
    v._validate_language_field(lg3, {"language": "python"})
    assert not lg3.warnings


def test_exclude_field():
    v._validate_exclude_field(log(), {})
    lg = log()
    v._validate_exclude_field(lg, {"exclude": "x"})
    assert lg.warnings
    lg2 = log()
    v._validate_exclude_field(lg2, {"exclude": ["ok", 5]})
    assert lg2.warnings  # non-string path


# --- config fields aggregation ---------------------------------------------
def test_config_fields_templates_include_invalid():
    lg = log()
    assert v._validate_config_fields(lg, {"repository": "a/b", "templates": "x"}) is False
    lg2 = log()
    assert v._validate_config_fields(lg2, {"repository": "a/b", "include": "x"}) is False


# --- full validate() + main() ----------------------------------------------
def _repo(tmp_path, body, language_files=None):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".rhiza").mkdir()
    (tmp_path / ".rhiza" / "template.yml").write_text(body)
    for rel in language_files or []:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")


def test_validate_go_end_to_end(tmp_path):
    _repo(
        tmp_path,
        'repository: "a/b"\nlanguage: go\nprofiles:\n  - github-project\nref: main\n',
        ["go.mod"],
    )
    assert v.validate(log(), tmp_path) is True


def test_validate_fails_on_bad_config(tmp_path):
    _repo(tmp_path, "language: go\nprofiles:\n  - github-project\n", ["go.mod"])  # no repository
    assert v.validate(log(), tmp_path) is False


def test_main_json_and_path_to_template(tmp_path, capsys):
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "template.yml").write_text('repository: "a/b"\nprofiles: [github-project]\n')
    rc = v.main([str(tmp_path), "--path-to-template", str(tmp_path), "--json", "--verbose"])
    assert rc == 0
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True


def test_main_returns_one_on_failure(tmp_path):
    assert v.main([str(tmp_path)]) == 1  # not a git repo
