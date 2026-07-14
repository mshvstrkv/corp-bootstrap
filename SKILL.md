---
name: corp-bootstrap
description: Official internal platform migration Skill for Java Spring Boot services. Use for GitVerse to Sber Bitbucket migration today, and for standards-driven analysis, dry-run planning, rollback-aware migration, and future corporate platform modernization workflows through plugins.
---

# Corp Bootstrap

Use this Skill when a developer wants to analyze, sync branches, plan, dry-run, migrate, moduleize a new single-module Maven project, update an existing corporate branch from GitVerse, or apply post-migration maintenance tasks for a Java Spring Boot service.

Current supported path: GitVerse to Sber corporate Bitbucket migration.

Default posture: experienced platform engineer. Synchronize all source branches first, ask for the primary development branch and corporate branch name, validate the existing modular layout, produce a migration plan, ask for confirmation, then execute with progress updates and a final report.

## Operating Model

`corp-bootstrap` v2 is a plugin-based migration framework:

- `bootstrap.py` only handles interaction and orchestration.
- `plugins/` contains migration capabilities.
- `standards/` contains corporate standards and plugin registration.
- `corporate-reference/` contains Maven golden reference files.
- `templates/` contains non-Maven generated resources.
- `references/` contains operator and maintainer guidance.

Do not hardcode corporate dependencies, Maven plugins, annotation processors, cleanup targets, template names, branch suffixes, or platform versions in Python.

## Maven Migration Rule

Never reconstruct POM files manually. Always invoke `bootstrap.py`. If generated Maven files do not match corporate golden references, stop and report a Skill bug.

Maven migration is owned by the Python implementation:

- root POM is rendered from `corporate-reference/root-pom.xml` with allowed placeholder replacement only;
- app POM is rendered from `corporate-reference/app-pom.xml`, then original business dependencies are merged by dependency identity;
- distributive files are copied from golden references under `corporate-reference/` with allowed placeholder replacement only;
- IDE assistants such as GigaCode must not manually edit root POM, app POM, or distributive files.

## Commands

```bash
python3.11 bootstrap.py analyze --project /path/to/project
python3.11 bootstrap.py sync
python3.11 bootstrap.py moduleize --project /path/to/project
python3.11 bootstrap.py apply --project /path/to/project --tasks logger
python3.11 bootstrap.py update --project /path/to/project
python3.11 bootstrap.py dry-run
python3.11 bootstrap.py migrate
```

Non-interactive sync:

```bash
python3.11 bootstrap.py sync \
  --gitverse-url https://gitverse.example/service.git \
  --bitbucket-url https://bitbucket.example/service.git
```

Apply selected maintenance tasks:

```bash
python3.11 bootstrap.py apply \
  --project /path/to/local/repo \
  --branch develop-corp \
  --tasks logger,cleanup \
  --yes
```

Update an existing corporate branch from GitVerse:

```bash
python3.11 bootstrap.py update \
  --project /path/to/local/repo \
  --source-branch develop \
  --target-branch develop-corp \
  --tasks logger \
  --commit \
  --push
```

When updating an existing corporate branch, never infer the GitVerse source branch. Always ask which source branch should be merged. Use `update`, not `sync`, for this workflow.

Non-interactive migration:

```bash
python3.11 bootstrap.py migrate \
  --gitverse-url https://gitverse.example/service.git \
  --bitbucket-url https://bitbucket.example/service.git \
  --branch develop \
  --corporate-branch develop-corp \
  --yes
```

`--branch` means primary development branch. `--corporate-branch` optionally sets the corporate branch name. `--yes` confirms the generated plan for non-interactive runs.

## Conversation Flow

For `migrate` and `dry-run`:

1. Ask for the GitVerse repository URL.
2. Ask for the Bitbucket repository URL.
3. Clone GitVerse.
4. Read all remote branches and synchronize all branches to Bitbucket for `migrate`.
5. Ask which branch is the primary development branch.
6. Ask for the corporate branch name, defaulting to `<primary>-corp`.
7. Validate the project and verify exactly one existing `*-app` module.
8. Generate and display the migration plan.
9. Ask for confirmation before migration edits.
10. Run plugins with progress updates.
11. Print final report and recommended next steps.

For exploratory requests, run `analyze` first.

If analysis or migration validation finds exactly one existing `*-app` module, use `migrate` for corporate migration. If no `*-app` module exists, ask the developer whether this is:

1. an existing project that must be fixed manually, or
2. a new project that should be converted using `moduleize`.

Never run `moduleize` automatically without explicit confirmation.

For `sync`:

1. Ask for the GitVerse repository URL if missing.
2. Ask for the Bitbucket repository URL if missing.
3. Clone and fetch GitVerse.
4. Read only `refs/heads/*`.
5. Configure the Bitbucket remote.
6. Push each branch using explicit `refs/remotes/origin/<branch>:refs/heads/<branch>`.
7. Print total, created, updated, skipped, and failed branches.

`sync` must not select a primary branch, create a corporate branch, run migration plugins, edit files, commit, run cleanup, or force-push.

For `apply`:

1. Require `--project`.
2. Validate that `--project` is an existing Git repository.
3. Validate the requested branch when `--branch` is provided, then checkout it after confirmation.
4. Verify exactly one existing `*-app` module.
5. Validate `--tasks`.
6. Show an apply plan.
7. Run only the requested tasks: `logger`, `cleanup`, or `maven`.
8. Commit only when `--commit` is passed and changes exist.
9. Push only when `--push` is passed.

`apply` must not clone GitVerse, synchronize branches, create a corporate branch, run unrequested tasks, commit without `--commit`, push without `--push`, or force-push.

For `moduleize`:

1. Require `--project`.
2. Validate that `--project` exists, is a Git repository, has root `pom.xml`, has root `src/`, has no existing `*-app` module, has no target module directory, and has a clean working tree.
3. If `--module-name` is omitted, suggest `<root-artifactId>-app` and ask for confirmation or another name.
4. Show the moduleization plan and ask for confirmation unless `--yes`.
5. Convert the root POM into an aggregator POM, preserving the Spring Boot parent, root coordinates, shared properties, and adding the new module.
6. Create `<module-name>/pom.xml` with the root project as parent and transfer application dependencies, build, profiles, name, and description.
7. Move root `src/` to `<module-name>/src/` without modifying source file contents.
8. Commit only when `--commit` is passed and changes exist.

`moduleize` must not create distributive, migrate Maven to corporate standards, modify Java logging, run cleanup, push changes, or run automatically when a project is missing an app module.

For `update`:

1. Require `--project`.
2. Validate that `--project` is an existing local Git repository.
3. Fetch GitVerse and Bitbucket remotes, normally `origin` and `bitbucket`.
4. If `--target-branch` is omitted, ask which existing corporate branch should be updated.
5. If `--source-branch` is omitted, show GitVerse branches with commits not in the target branch and ask which branch to merge. If one branch has new commits, still show it and ask.
6. Show an update plan and ask for confirmation unless `--yes`.
7. Checkout the existing target branch from Bitbucket.
8. Merge the selected GitVerse source branch.
9. If conflicts occur, stop before apply tasks, commit, or push. Report conflicted files and root `src/` added-file hints only.
10. Run only requested tasks after a successful merge. Default task is `logger`.
11. Commit only when `--commit` is passed and changes exist.
12. Push only when `--push` is passed. Never force-push.

`update` must not clone, mirror all branches, create a corporate branch, run full migration, run unrequested tasks, or guess the source branch. If `--yes` is used, both `--source-branch` and `--target-branch` are required.

When a developer asks "обнови develop-corp из GitVerse", ask: "Из какой GitVerse ветки мержить изменения в develop-corp?" Do not assume `develop` or any other source branch.

## Modes

- `analyze`: inspect a local checkout only. No clone, commit, push, or file mutation.
- `sync`: clone GitVerse and synchronize `refs/heads/*` to Bitbucket only. No corporate branch, migration edits, plugins, commit, or force-push.
- `moduleize`: convert a new single-module Maven Spring Boot project into a root aggregator plus one application module. No corporate migration, distributive, logger migration, cleanup, or push.
- `apply`: run selected post-migration tasks on an existing local corporate branch. No GitVerse clone, branch synchronization, corporate branch creation, unrequested tasks, commit, or push by default.
- `update`: merge a selected GitVerse branch into a selected existing corporate branch, then optionally run selected apply tasks.
- `dry-run`: clone, read branches, ask for primary and corporate branch names, validate, and print the execution plan. No push, migration edits, or commit.
- `migrate`: execute the confirmed plugin plan.

Mode intent:

- `sync`: only GitVerse to Bitbucket branch synchronization.
- `migrate`: first-time corporate migration.
- `moduleize`: new-project Maven module conversion only.
- `apply`: post-migration maintenance on an existing corporate branch.
- `update`: post-migration integration from GitVerse into an existing corporate branch.

Never manually run `git pull origin develop`, `git push bitbucket develop:develop-corp`, or `git merge origin/develop` to update a corporate branch. Invoke `python3 bootstrap.py update ...`.

## Out Of Scope Contract

This Skill must never modify:

- business logic;
- REST API;
- DTOs;
- SQL;
- Liquibase;
- Flyway;
- application business configuration.

If a requested migration requires those areas, stop and explain that a service-owned change is required outside this Skill.

## Stop Conditions

Stop with a readable error when:

- GitVerse URL, Bitbucket URL, or branch selection is missing or invalid.
- Git authentication, clone, checkout, remote configuration, push, or commit fails.
- Expected layout is missing: root `pom.xml`, exactly one existing `*-app` module, `<module>/pom.xml`, or `<module>/src`.
- No application module exists or multiple `*-app` modules exist.
- `moduleize` is requested for a project with an existing `*-app` module, missing root `src/`, a target module directory that already exists, or a dirty working tree.
- a POM is invalid XML.
- the distributive POM template is invalid or is not a distributive module POM.
- required Maven coordinates for generated distributive files cannot be resolved.
- requested standards are not represented in `standards/` and `plugins/`.

Never expose stack traces to developers.

## Plugin Lifecycle

Each plugin exposes:

- `validate(context)`;
- `plan(context)`;
- `execute(context, dry_run=False)`;
- `rollback(context)`.

Adding a new migration should require one new plugin and one registration entry in `standards/plugins.yaml`.

## Rollback Rules

Rollback is best effort:

- restore local working tree when possible;
- delete the selected local corporate branch when created by the workflow;
- delete the selected remote corporate branch when safe and permissions allow;
- clean the temporary clone automatically for rollback and dry-run when the workspace was created by the tool.

Never claim rollback succeeded unless the report shows the completed rollback actions. The original pushed branch is not deleted automatically.

## Reporting

Reports must include:

- platform analysis or migration plan;
- selected source and target repositories;
- primary development branch and corporate branch;
- completed plugin steps;
- warnings and rollback limitations;
- platform standard version and latest standard version when analyzing;
- recommended next steps.

## Reference Files

Read only when needed:

- `references/operator-playbook.md`: interaction design, progress updates, confirmation, and recovery.
- `references/corporate-standards.md`: current config-driven corporate standards.
- `references/maintainer-guide.md`: plugin architecture, compatibility, versioning, rollback, and release process.
