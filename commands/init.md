---
description: Bootstrap a rhiza-managed repo in the current folder (empty, or an existing git repo that isn't yet rhiza-managed) — git init if needed, ask whether it lives on GitHub or GitLab (auto-detecting an existing remote), ask owner/name/visibility, scaffold .rhiza/template.yml with the matching platform profile, create or reuse the remote (gh/glab), push, then apply the template with a first sync.
argument-hint: "[repo name]  (optional; defaults to the current folder name)"
allowed-tools: Bash(git*), Bash(gh*), Bash(glab*), Bash(uvx*), Bash(make*), Bash(python3*), Bash(cat*), Bash(ls*), Bash(basename*), Bash(pwd*), Read, Write, AskUserQuestion
---

You are running `/init` in the **current working directory**. Goal: turn this
folder into a fresh **rhiza-managed** repository — initialise git (if it isn't
already), decide where it lives (GitHub or GitLab), scaffold the `.rhiza/` config
for that platform, create (or reuse) the remote, push, and apply the rhiza
template with a first sync. After this runs, the repo is a normal rhiza-managed
repo where `/boost`, `/quality`, and `make sync` all work.

The folder may be **empty** or may **already contain a git repo** (a `.git/` you
`git init`'d earlier, possibly with commits and even an `origin` remote) — as
long as it isn't rhiza-managed yet. Detect which case you're in and adapt: never
re-init an existing repo, and never clobber an existing remote.

Argument (optional): `$ARGUMENTS` — the repository name. If empty, default to the
current folder's basename.

**Chicken-and-egg note.** The `Makefile` and `.rhiza/rhiza.mk` (which provide the
`make sync` target) are themselves delivered *by* the template. A brand-new folder
has neither, so the **first** sync is bootstrapped by invoking the rhiza CLI
directly with `uvx` (step 8), not `make sync`. Every sync *after* this one uses
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
  sync in step 8. If missing, you can still scaffold and push (steps 2–7) — warn
  that the user must install `uv` and run the first sync manually.

## 2. git init (only if needed)
- If `HAS_GIT` is false, `git init -b main` (default branch `main`). If the
  installed git is too old for `-b`, run `git init` then
  `git symbolic-ref HEAD refs/heads/main`.
- If `HAS_GIT` is true, **skip init entirely** — the repo already exists. Keep its
  current branch; do not rename or reset it.

## 3. Choose the platform (GitHub vs GitLab)
- **If `EXISTING_ORIGIN` was found in step 1**, detect the host from its URL
  (`github.com` → GitHub; `gitlab.com` or a self-hosted GitLab host → GitLab) and
  make **that the recommended, first option**. The remote already exists, so
  step 7 will skip creation and just push to it.
- **Otherwise** (no origin) list **GitHub first and marked "(Recommended)"**,
  GitLab second.

Present the menu with `AskUserQuestion`:
- **GitHub** → platform `github`, profile `github-project`, CLI `gh`.
- **GitLab** → platform `gitlab`, profile `gitlab-project`, CLI `glab`.

Verify the chosen platform's CLI is installed and authenticated
(`gh auth status` / `glab auth status`). If it isn't, tell the user how to fix it
(`gh auth login` / `glab auth login`) and stop before creating anything remote —
but you may still complete the local scaffold (steps 4–6) and report that the
remote/push/sync (steps 7–9) are pending auth.

## 4. Collect repo details (ask each run)
Gather via `AskUserQuestion` (offer sensible defaults, let the user override):
- **Owner / namespace** — the GitHub org-or-user, or GitLab group/namespace, that
  will own the repo. If `EXISTING_ORIGIN` was found, parse its owner as the
  default; otherwise no safe default — ask.
- **Repository name** — default to the name parsed from `EXISTING_ORIGIN` if
  present, else `$ARGUMENTS` if given, else `basename "$PWD"`.
- **Visibility** — private (recommended default) or public. Skip this if
  `EXISTING_ORIGIN` was found (the remote already exists with its own visibility;
  don't try to change it).

Hold these as `OWNER`, `NAME`, `VISIBILITY` for the remaining steps. The full
slug is `OWNER/NAME`. When `EXISTING_ORIGIN` is present, `OWNER/NAME` should
match it — if the user's answers diverge from the existing remote, stop and ask
which they mean rather than guessing.

## 5. Resolve the template version
- Template content version: latest `jebel-quant/rhiza` release —
  `gh release list -R jebel-quant/rhiza -L 1 --json tagName --jq '.[0].tagName'`
  (this read works even for a GitLab-hosted target; it's just querying the public
  rhiza repo). If `gh` is unavailable, ask the user for the tag (e.g. `v1.1.3`).
- Tool version: pin `0.18.0` (the version the fleet currently runs). This is the
  **rhiza CLI** version and is decoupled from the template content version above —
  do not derive one from the other.

## 6. Scaffold `.rhiza/` and the initial commit
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

Then commit the new config. Word the message to match the starting state:
- `git add .rhiza`
- If the repo had **no commits yet** (fresh `git init`, or an unborn branch):
  `git commit -m "chore: initialise rhiza-managed repo"`
- If the repo **already had commits**:
  `git commit -m "chore: add rhiza template config"`

## 7. Create or reuse the remote, then push
- **If `EXISTING_ORIGIN` was found in step 1**, the remote already exists — do
  **not** create it. Just push the current branch:
  `git push -u origin "$(git branch --show-current)"`. If the push is rejected
  because the remote has commits you don't have locally, stop and report — don't
  force-push.
- **Otherwise, create the remote** with the platform CLI from step 3 and push:
  - **GitHub:**
    `gh repo create "$OWNER/$NAME" --<private|public> --source=. --remote=origin --push`
  - **GitLab:** create the project, wire up `origin`, and push. Depending on
    `glab` version:
    `glab repo create "$OWNER/$NAME" --<private|public>` then
    `git remote add origin <the URL glab prints>` and
    `git push -u origin main`. (Some `glab` versions can do this in one step with
    `--push`; use it if available.)
  - If creation fails because the name is already taken remotely, stop and report
    — do not overwrite or force-push into it. (If it's actually *your* repo, the
    user can add it as `origin` and re-run; `/init` will then take the reuse path.)

## 8. Bootstrap the first sync
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
- If the folder **already had files** (the pre-existing-repo case), the sync may
  report conflicts or leave `.rej` files where a template file overlaps something
  you already had. Resolve them the same way `/boost` does — take the **upstream
  (template) side** — then continue; if anything is ambiguous, stop and show the
  conflicting files rather than guessing.

## 9. Commit + push the sync
- `git add --all`
- If `git diff --cached --name-only` is non-empty:
  - `git commit -m "chore: apply rhiza sync <TARGET tag>"`
  - `git push`
- Else report "sync produced no files" (unexpected — flag it).

## 10. Report
Summarise concisely: the repo slug (`OWNER/NAME`) and its URL, platform + profile,
visibility, template tag and pinned tool version, the two commits made, and the
count of files the sync added. Point the user at next steps: fill in `README.md`
with `/revisit`, and run `/quality` to see the initial scorecard.
