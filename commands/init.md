---
description: Bootstrap a rhiza-managed repo in the current folder (empty, or an existing git repo that isn't yet rhiza-managed) — git init if needed, ask whether it lives on GitHub or GitLab (auto-detecting an existing remote), ask owner/name/visibility, optionally scaffold a minimal Python project (pyproject.toml + src/ + tests/), then put the .rhiza scaffold and the first template sync on a `rhiza_init_<date>` branch and open a PR. Never pushes rhiza changes straight to the default branch.
argument-hint: "[repo name]  (optional; defaults to the current folder name)"
allowed-tools: Bash(git*), Bash(gh*), Bash(glab*), Bash(uvx*), Bash(make*), Bash(python3*), Bash(cat*), Bash(ls*), Bash(basename*), Bash(pwd*), Bash(date*), Read, Write, AskUserQuestion
---

You are running `/init` in the **current working directory**. Goal: turn this
folder into a fresh **rhiza-managed** repository — initialise git (if it isn't
already), decide where it lives (GitHub or GitLab), scaffold the `.rhiza/` config
for that platform, apply the rhiza template with a first sync, and **open a PR**
with that work. After it merges, the repo is a normal rhiza-managed repo where
`/boost`, `/quality`, and `make sync` all work.

The folder may be **empty** or may **already contain a git repo** (a `.git/` you
`git init`'d earlier, possibly with commits and even an `origin` remote) — as
long as it isn't rhiza-managed yet. Detect which case you're in and adapt: never
re-init an existing repo, and never clobber an existing remote.

**Never push rhiza changes to the default branch.** The `.rhiza` scaffold and the
template sync (which can be hundreds of files, including CI) go on a dedicated
`rhiza_init_<date>` branch and are delivered as a PR, so they get reviewed — this
matters most in an existing repo whose default branch may be protected. The only
thing that ever lands on the default branch directly is the empty initial commit
that seeds a brand-new repo (step 6), because a PR needs a base branch to exist.

Argument (optional): `$ARGUMENTS` — the repository name. If empty, default to the
current folder's basename.

**Chicken-and-egg note.** The `Makefile` and `.rhiza/rhiza.mk` (which provide the
`make sync` target) are themselves delivered *by* the template. A brand-new folder
has neither, so the **first** sync is bootstrapped by invoking the rhiza CLI
directly with `uvx` (step 9), not `make sync`. Every sync *after* this one uses
`make sync`.

Work through these steps. Stop and report if a precondition fails.

## 1. Preconditions — and detect the starting state
- **Already rhiza-managed?** If `.rhiza/template.yml` exists, abort and point at
  `/boost` — this command is for repos that aren't managed yet.
- **Is there already a git repo?** Run `git rev-parse --is-inside-work-tree`
  (ignore its error if absent). Record `HAS_GIT` accordingly. If yes, capture the
  existing state — you'll reuse it, not recreate it:
  - current branch — `git branch --show-current` (may be empty on an
    unborn branch with no commits);
  - whether any commits exist — `git rev-list -n1 --all` (empty output ⇒ no
    commits yet);
  - existing `origin` remote, if any — `git remote get-url origin`
    (record as `EXISTING_ORIGIN`).
- **Folder contents.** Run `ls -A`. If it contains files beyond an expected
  `.git/` and ordinary dotfiles, list them and ask the user (`AskUserQuestion`)
  whether to proceed — `/init` layers `.rhiza/` config plus a large template sync
  on top of whatever is here. Do not proceed without a yes.
- Confirm `uvx` is available (`uvx --version`). It's required for the bootstrap
  sync in step 9. If missing, you can still scaffold, branch, and (for a
  brand-new repo) create the remote — but warn that the user must install `uv`
  and run the first sync manually before the PR is meaningful.

## 2. git init (only if needed)
- If `HAS_GIT` is false, `git init -b main` (default branch `main`). If the
  installed git is too old for `-b`, run `git init` then
  `git symbolic-ref HEAD refs/heads/main`.
- If `HAS_GIT` is true, **skip init entirely** — the repo already exists. Keep its
  current branch; do not rename or reset it.

> **Shortcut for a fully-fledged repo.** If `EXISTING_ORIGIN` was found in
> step 1, the repo already exists remotely — its platform, owner, and name are
> all determined by that remote, so **skip the questions in steps 3 and 4
> entirely**. Derive everything from the URL, report what you detected, and go
> straight to step 5:
> - platform/profile from the host (`github.com` → GitHub/`github-project`;
>   `gitlab.com` or a self-hosted GitLab host → GitLab/`gitlab-project`);
> - `OWNER`/`NAME` from the URL path;
> - no `VISIBILITY` — the remote already has one; `/init` won't change it.
>
> Steps 3 and 4 below are **only** for the no-remote (empty-folder) case. Note
> that opening the PR (step 10) still needs the platform CLI (`gh`/`glab`) even
> on this path; if it's unavailable, `/init` pushes the branch and hands you a
> "create PR" URL instead.

## 3. Choose the platform (GitHub vs GitLab)
No `origin` remote to go on, so ask where the repo shall live. Present the menu
with `AskUserQuestion`, **GitHub first and marked "(Recommended)"**, GitLab
second:
- **GitHub** → platform `github`, profile `github-project`, CLI `gh`.
- **GitLab** → platform `gitlab`, profile `gitlab-project`, CLI `glab`.

Verify the chosen platform's CLI is installed and authenticated
(`gh auth status` / `glab auth status`). If it isn't, tell the user how to fix it
(`gh auth login` / `glab auth login`) and stop before creating anything remote —
but you may still complete the local scaffold on the work branch (steps 4–9) and
report that the remote/push/PR (steps 6–10) are pending auth.

## 4. Collect repo details (ask each run)
Gather via `AskUserQuestion` (offer sensible defaults, let the user override):
- **Owner / namespace** — the GitHub org-or-user, or GitLab group/namespace, that
  will own the repo. No safe default; ask.
- **Repository name** — default to `$ARGUMENTS` if given, else `basename "$PWD"`.
- **Visibility** — private (recommended default) or public.

Hold these as `OWNER`, `NAME`, `VISIBILITY` for the remaining steps. The full
slug is `OWNER/NAME`.

## 5. Resolve the template version
- Template content version: latest `jebel-quant/rhiza` release —
  `gh release list -R jebel-quant/rhiza -L 1 --json tagName --jq '.[0].tagName'`
  (this read works even for a GitLab-hosted target; it's just querying the public
  rhiza repo). If `gh` is unavailable, ask the user for the tag (e.g. `v1.1.3`).
- Tool version: pin `0.18.0` (the version the fleet currently runs). This is the
  **rhiza CLI** version and is decoupled from the template content version above —
  do not derive one from the other.

## 6. Establish the remote and the default branch
Every rhiza change goes on a branch (step 7) and out as a PR (step 10), so first
make sure there's a remote **and** a non-empty default branch to be the PR base.
Determine the default branch name `DEFAULT` (existing repo:
`git remote show origin` / `gh repo view --json defaultBranchRef`; brand-new:
`main`).

- **Brand-new repo (no `origin`, no commits):**
  - Seed the default branch with an **empty** initial commit so it can serve as a
    PR base: `git commit --allow-empty -m "chore: initialise repository"`.
  - Create the remote and push only `DEFAULT`:
    - **GitHub:**
      `gh repo create "$OWNER/$NAME" --<private|public> --source=. --remote=origin --push`
    - **GitLab:** `glab repo create "$OWNER/$NAME" --<private|public>`, then
      `git remote add origin <the URL glab prints>` and
      `git push -u origin "$DEFAULT"`.
  - If creation fails because the name is already taken remotely, stop and report
    — do not overwrite or force-push. (If it's actually *your* repo, add it as
    `origin` and re-run; `/init` will take the existing-remote path.)
- **Existing repo with `origin`:** don't create anything. Fetch so the branch is
  based on the current tip: `git fetch origin`. If the repo had commits on an
  unpushed local default branch but no remote default yet, push it first
  (`git push -u origin "$DEFAULT"`) so the PR has a base.

## 7. Create the work branch
- `BRANCH=rhiza_init_$(date +%Y%m%d)`. If that branch already exists locally or on
  the remote, disambiguate with a time suffix: `rhiza_init_$(date +%Y%m%d-%H%M%S)`.
- Branch off the up-to-date default — **never commit the rhiza work onto
  `DEFAULT`**:
  - existing remote: `git checkout -b "$BRANCH" "origin/$DEFAULT"`;
  - brand-new (default only exists locally so far): `git checkout -b "$BRANCH"`.

## 8. Scaffold `.rhiza/` and commit (on the branch)
Write two files (create the `.rhiza/` directory first):

`.rhiza/template.yml`:
```yaml
template-repository: "jebel-quant/rhiza"
template-branch: "<TARGET tag from step 5>"

profiles:
  - <github-project | gitlab-project>   # per step 3
```

`.rhiza/.rhiza-version`:
```
0.18.0
```

Then commit:
- `git add .rhiza`
- `git commit -m "chore: add rhiza template config"`

## 9. Bootstrap the first sync (on the branch)
The Makefile doesn't exist yet, so run the rhiza CLI directly (pinned to the tool
version from step 5):
```bash
uvx "rhiza==0.18.0" sync .
```
This materialises the template for the chosen profile — the `Makefile`,
`.rhiza/rhiza.mk`, CI workflows (`.github/workflows/*` for GitHub or
`.gitlab-ci.yml` for GitLab), and the rest.
- On a truly **empty** folder there's nothing to conflict with, so a non-zero
  exit is unexpected — capture the output and report it rather than papering
  over it.
- If the folder **already had files**, the sync may report conflicts or leave
  `.rej` files where a template file overlaps something you already had. Resolve
  them the same way `/boost` does — take the **upstream (template) side** — then
  continue; if anything is ambiguous, stop and show the conflicting files rather
  than guessing.

Then commit the sync output:
- `git add --all`
- If `git diff --cached --name-only` is non-empty:
  `git commit -m "chore: apply rhiza sync <TARGET tag>"`
- Else report "sync produced no files" (unexpected — flag it).

### Optional project scaffolding
Offer, don't impose. Ask with an `AskUserQuestion` **multi-select**
(`multiSelect: true`) which of these to add — recommend all for a brand-new
empty repo, none if the repo already has them. Create **only what's missing**;
never overwrite an existing file (skip it and say so). Let `PKG` be `NAME`
lowercased with non-identifier characters (e.g. `-`) turned into `_`.

- **Python package skeleton** — `pyproject.toml` + `src/$PKG/` + `tests/`:
  - `pyproject.toml` with a minimal `[project]` (`name = "$NAME"`,
    `version = "0.0.0"`, `requires-python`, empty `dependencies`) and a
    `[build-system]`, if absent.
  - `src/$PKG/__init__.py` (a one-line docstring), if `src/` has no package yet.
  - `tests/test_smoke.py` with a single trivial passing test, if `tests/` is empty.
- **`mkdocs.yml`** — a minimal config (`site_name: $NAME`, `theme: material`,
  `docs_dir: docs`, a Home → `index.md` nav entry) plus a placeholder
  `docs/index.md`, if `mkdocs.yml` is absent. Tell the user this is a bare
  starting point — **`/revisit`** produces the full docs set (README + CLAUDE.md
  + a richer mkdocs.yml with badges and API docs) and is the better tool once the
  repo has content.

If anything was created, commit it separately on the branch:
`git commit -m "chore: scaffold minimal project layout"`. If the user picked
nothing (or everything already existed), skip this commit silently.

## 10. Push the branch and open the PR
- `git push -u origin "$BRANCH"`.
- Open a PR/MR from `$BRANCH` into `$DEFAULT` with the platform CLI:
  - **GitHub:** `gh pr create --base "$DEFAULT" --head "$BRANCH" --title "chore: initialise rhiza-managed repo (<TARGET tag>)" --body-file <BODY>`
  - **GitLab:** `glab mr create --source-branch "$BRANCH" --target-branch "$DEFAULT" --title "chore: initialise rhiza-managed repo (<TARGET tag>)" --description-file <BODY>`
  - The body should note: platform/profile, template tag + pinned tool version,
    that it seeds the repo as rhiza-managed, and that CI arrives with this PR.
- If the platform CLI is unavailable or unauthenticated, don't fail — the branch
  is already pushed; print the branch name and the "create a PR" compare URL so
  the user can open it in the browser.

## 11. Report
Summarise concisely: the repo slug (`OWNER/NAME`) and its URL, platform + profile,
visibility (for a new repo), template tag and pinned tool version, the work branch
name, the commits on it, the count of files the sync added, any optional
scaffolding created (or skipped as already-present), and the **PR URL** (or the
manual compare URL if the CLI was unavailable). Point the user at next steps:
review + merge the PR, then flesh out the docs with `/revisit` and run `/quality`
for the initial scorecard.
