# Operator Playbook

Use this file for interaction design, confirmation, progress updates, failure recovery, and developer experience.

## Intent Routing

- "Can this be migrated?", "check readiness", "what will change": run `analyze`.
- "Show me what would happen", "dry run": run `dry-run`.
- "Migrate", "create the corp branch", or explicit confirmation after dry-run: run `migrate`.
- "Update develop-corp from GitVerse", "pull new GitVerse changes into the corporate branch": run `update`.
- "Apply logger/cleanup/Maven tasks to an existing branch without merging GitVerse": run `apply`.
- "Upgrade Spring Boot", "upgrade Java", "modernize dependencies": explain that v2 is architected for those plugins, but they are not implemented unless registered in `standards/plugins.yaml`.

Do not use `sync` for corporate branch updates. `sync` mirrors GitVerse branches to Bitbucket only. `update` is the only mode that merges a GitVerse branch into an existing corporate branch.

## Conversation Flow

Use one short prompt at a time:

```text
Please provide the GitVerse repository URL.
Please provide the Bitbucket repository URL.
Reading available Git branches...
Synchronizing all GitVerse branches to Bitbucket...
Which branch is the primary development branch?
1. develop
2. release
3. feature/payment
Corporate branch name
Default:
develop-corp
Press Enter to accept or type another name.
```

After validation, show the generated plan before repository modification:

```text
Migration Plan
OK Synchronize all GitVerse branches to Bitbucket
OK Create corporate branch develop-corp
OK Generate root pom from corporate golden reference
OK Generate app pom from corporate golden reference and merge business dependencies
OK Generate distributive from corporate golden references
OK Cleanup legacy build and deployment files
OK Java logger migration
OK Create Corporate migration commit
OK Push completed migration to develop-corp
```

Then summarize:

```text
Source: <gitverse-url>
Target: <bitbucket-url>
Primary development branch: develop
Corporate branch: develop-corp
Proceed with migration?
```

For update, never infer the GitVerse source branch. If the developer says "обнови develop-corp из GitVerse", ask:

```text
Из какой GitVerse ветки мержить изменения в develop-corp?
```

Fetch both remotes, show candidate branches, and ask even when only one branch has new commits:

```text
GitVerse branches with commits not in develop-corp:
1. develop (+10 commits)
2. module (+2 commits)

Which branch should be merged into the corporate branch?
```

Then show the update plan:

```text
Update Plan

Project:
  /path/to/repo

Source branch:
  origin/develop

Target branch:
  bitbucket/develop-corp

Tasks after merge:
  logger

Will perform:
  fetch origin
  fetch bitbucket
  checkout develop-corp
  merge origin/develop
  apply logger
  commit
  push

Will NOT:
  sync all branches
  create corporate branch
  run full migration
  run Maven unless requested
  run cleanup unless requested
  force-push
```

## Progress Updates

Use short updates:

- validating repository access;
- reading remote branches;
- synchronizing all branches to Bitbucket;
- asking for the primary development branch;
- asking for the corporate branch name;
- validating exactly one existing `*-app` module;
- building migration plan;
- running migration plugins;
- creating commit and pushing corporate branch;
- generating final report.

For update, add:

- fetching GitVerse and Bitbucket remotes;
- listing source branches with new commits relative to the target branch;
- asking for the GitVerse source branch;
- asking for the existing corporate target branch when omitted;
- checking out the target branch;
- merging the selected source branch;
- running selected post-merge tasks only after a clean merge;
- committing and pushing only when requested.

Do not imply source files were modified before the migration has been confirmed.

## Error Recovery

Clone failure:

- likely causes: URL typo, missing VPN, missing credentials, repository does not exist;
- recovery: fix access or URL, then rerun.

Push failure before migration edits:

- local source files have not been intentionally migrated, but some Bitbucket branches may already have been synchronized;
- recovery: fix Bitbucket access or branch permissions, then rerun in a clean workspace.

Failure after corporate branch creation:

- rollback attempts local worktree restore and corporate branch deletion;
- remote deletion may fail due to permissions or branch protection;
- inspect Bitbucket branch state before retry.
- default temporary workspaces are removed during rollback when possible; explicit `--workspace` checkouts remain for operator inspection.

Validation failure:

- no migration plugins should have changed files;
- if the error says application module missing, create the `*-app` module before rerunning;
- if multiple `*-app` modules exist, resolve the project structure before rerunning;
- recovery: fix layout or use a custom migration outside this Skill.

Final push failure:

- local workspace may contain completed migration edits and a commit;
- recovery: keep the workspace for inspection, fix credentials or branch permissions, then push manually if the diff is correct.

Update merge conflict:

- stop immediately;
- do not run apply tasks;
- do not commit;
- do not push;
- print conflicted files;
- if files were added under root `src/`, report them as hints only because they probably need to move into `<app-module>/src/`;
- tell the developer to resolve conflicts manually, then run `python3 bootstrap.py apply --project <repo> --branch <target> --tasks <tasks> --commit --push` when ready.

## Developer Experience Rules

- Keep prompts concise.
- Preserve branch names exactly as Git reports them.
- Explain what was modified and what was intentionally left untouched.
- Never manually edit Maven files when using this Skill. Invoke `bootstrap.py`; Maven output must come from `corporate-reference/`. If generated Maven files are wrong, report a Skill bug.
- Never manually update corporate branches with `git pull origin develop`, `git merge origin/develop`, or `git push bitbucket develop:develop-corp`. Invoke `python3 bootstrap.py update ...`.
- Always state the pushed corporate branch.
- Mention the workspace path only when it was explicit or when the developer needs to inspect a failed migration.
- End with recommended next steps: review Bitbucket diff, run service tests, open the team migration pull request when appropriate.
- Do not paste stack traces.
