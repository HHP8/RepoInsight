# RepoInsight development in Codex Cloud

Use the existing [HHP8/RepoInsight repository](https://github.com/HHP8/RepoInsight)
with `codex/repoinsight-v2` as the expansion branch. Keep `main` as the stable
release branch. The current repository is public: commits pushed to development
branches are public too. A private cloud environment does not make the GitHub
repository or its branches private.

## Prepare the checkout

The development branch includes the published application and its hosted
validation and release-workflow fixes. The original local `codex/repoinsight-v1`
branch is preserved. Local `main` may be older than GitHub's `main`; use fetched
remote history when comparing changes.

For a fresh checkout:

```console
git clone --branch codex/repoinsight-v2 https://github.com/HHP8/RepoInsight.git
cd RepoInsight
python tools/cloud_setup.py --check
```

Requirements: Python 3.11 or newer, Git, and package-registry network access during
installation. Python 3.12 is a suitable development baseline. The setup script
creates a platform-specific `.venv`, upgrades pip to support dependency groups,
installs the editable application and development tools, checks dependencies,
and prints the CLI version. `--check` also runs formatting, lint, typing, and tests.

The setup script does not push commits, change branches, merge, publish a release,
or require application secrets. Do not upload the existing Windows `.venv`, caches,
reports, or build artifacts to the cloud.

## Create the cloud environment

Follow the current
[official OpenAI cloud environment guide](https://learn.chatgpt.com/docs/environments/cloud-environments).

1. Choose **Work in > Cloud > Select environment > Create environment**.
2. Select `HHP8/RepoInsight`. Reuse the existing GitHub connection if available.
3. Name the environment `RepoInsight development` and keep access limited to you.
4. Ask setup to use Python 3.12 and Git, prepare the source checkout with
   `python tools/cloud_setup.py --check`, and use the `.venv` interpreter for tasks.
5. Review the configuration, setup changes, and actual check results. Save and
   publish the environment only after setup succeeds.
6. Start development tasks from `codex/repoinsight-v2`. Verify the checked-out branch
   before making changes; create focused task branches from that baseline as needed.

Codex can record dependency preparation in an install script. RepoInsight is a CLI
and needs no background server or service startup command. Environment publication
saves the prepared development setup; package publication and Git merges remain
separate actions.

Package-registry access is sufficient for setup and the standard offline test suite.
Live analysis of a public GitHub repository additionally needs the relevant GitHub
network destinations. Enable that only when a task calls for a live smoke test.
RepoInsight development requires no OpenAI API key or PyPI publishing credential.

Use this task instruction after preparing the environment:

```text
Work on HHP8/RepoInsight. Read AGENTS.md. Inspect git status and the current branch.
Use codex/repoinsight-v2, or create a focused codex/ task branch from it. If the
workspace is on main or a detached HEAD, switch to the development branch before
editing, preserving any existing changes. Use the .venv Python interpreter.
Run the standard project checks. Keep any pull request in draft. Do not push to
main, merge, force-push, create release tags, publish packages, or deploy.
Report the branch, changes, validation results, and any remaining blockers.
```

## Keep stable releases protected

Use GitHub's `main` protection to require a pull request and the CI checks, apply
the rules to administrators, and prevent force pushes and deletion. Keep automatic
merging disabled. Agent instructions supplement these controls but do not enforce
GitHub permissions. Review protection settings on GitHub before relying on them.

CI runs on pushes to `main` and `codex/**` branches, and on pull requests. The
existing matrix checks Linux, macOS, and Windows on Python 3.11 through 3.14.
Branch pushes do not trigger the tag-based release workflow. PyPI publication
remains a separate manual action for a version tag.

Use focused commits and draft pull requests for review. Merging into `main` and
releasing the application require a separate explicit request. Saved cloud state
does not replace committing and pushing important work to the development branch.

## Initial expansion boundary

This setup establishes a development workflow; it does not select new application
features or change the package version. Before a substantial expansion, define
the desired user workflows and acceptance criteria, then implement focused changes
on task branches. Preserve the version 1 JSON contract, rule IDs, deterministic
scoring, offline report, and documented safety model until a design explicitly
changes those requirements.
