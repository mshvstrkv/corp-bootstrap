# corp-bootstrap

`corp-bootstrap` is the internal Codex Skill and Python 3.11 platform migration framework for Java Spring Boot services.

Version 2.0 keeps the current GitVerse to Sber corporate Bitbucket migration path, but the implementation is now plugin-based and standards-driven so future platform upgrades can be added without changing existing plugins.

## Current Capability

The current migration path:

- clones a GitVerse repository;
- reads all GitVerse remote branches;
- synchronizes all GitVerse branches to Bitbucket before migration edits;
- asks for the primary development branch;
- asks for the corporate branch name;
- validates that exactly one existing `*-app` application module is present;
- generates a migration plan;
- asks for confirmation before modifying repositories;
- creates and pushes the selected corporate branch;
- validates the expected Spring Boot Maven layout;
- renders root and app POM files from corporate golden references;
- creates the distributive module from corporate golden references;
- removes configured legacy build and deployment files;
- converts supported Java logger fields to Lombok `@Slf4j`;
- writes the platform standard marker;
- creates the `Corporate migration` commit;
- pushes the corporate branch and prints a final report.

The standalone sync path:

- clones a GitVerse repository;
- reads only GitVerse `refs/heads/*`;
- configures the Bitbucket remote;
- pushes all GitVerse branches to Bitbucket with explicit refs;
- prints created, updated, skipped, and failed branch counts;
- never creates a corporate branch, runs migration plugins, changes files, commits, or force-pushes.

The apply path:

- operates on an existing local corporate repository;
- optionally checks out an existing branch;
- applies selected tasks only: `logger`, `cleanup`, or `maven`;
- commits only with `--commit`;
- pushes only with `--push`;
- never clones GitVerse, synchronizes branches, or creates a corporate branch.

The update path:

- operates on an existing local corporate repository;
- fetches GitVerse and Bitbucket remotes;
- asks which existing corporate branch should be updated when omitted;
- asks which GitVerse branch should be merged when omitted;
- merges the selected GitVerse branch into the selected corporate branch;
- stops on merge conflicts before running apply tasks, commit, or push;
- optionally runs selected post-merge tasks: `logger`, `cleanup`, or `maven`;
- commits only with `--commit`;
- pushes only with `--push`;
- never clones, mirrors all branches, creates a corporate branch, runs full migration, guesses the source branch, or force-pushes.

## Modes

- `analyze`: inspect an existing local project without modifications.
- `dry-run`: clone, validate, select branch, and print the execution plan without migration edits.
- `migrate`: execute the confirmed plugin plan.
- `sync`: synchronize GitVerse branches to Bitbucket only.
- `apply`: run selected post-migration maintenance tasks on an existing local corporate branch.
- `update`: merge a selected GitVerse branch into a selected existing corporate branch, then optionally run selected apply tasks.

## Installation

Copy the full `corp-bootstrap/` directory into the company Codex Skills repository.

`SKILL.md` is the canonical Codex entrypoint. In packaging environments with a case-sensitive filesystem, lowercase `skill.md` may be kept as a byte-for-byte mirror for backward compatibility with the original repository contract.

Python requirement: 3.11.

Dependencies: Python standard library only.

## Usage

Analyze a local checkout:

```bash
python3.11 bootstrap.py analyze --project /path/to/service
```

Interactive dry-run:

```bash
python3.11 bootstrap.py dry-run
```

Interactive migration:

```bash
python3.11 bootstrap.py migrate
```

Branch sync only:

```bash
python3.11 bootstrap.py sync \
  --gitverse-url https://gitverse.example/service.git \
  --bitbucket-url https://bitbucket.example/service.git
```

Post-migration maintenance on an existing local repository:

```bash
python3.11 bootstrap.py apply \
  --project /path/to/local/repo \
  --branch develop-corp \
  --tasks logger,cleanup \
  --yes
```

Supported apply tasks are `logger`, `cleanup`, and `maven`. `apply` does not commit unless `--commit` is passed and does not push unless `--push` is passed.

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

If `--source-branch` is omitted, the tool fetches GitVerse, shows branches with commits not in the target branch, and asks which branch to merge. It never assumes `develop`, `module`, or any other source branch. If `--target-branch` is omitted, it asks for an existing corporate branch. `--yes` requires both `--source-branch` and `--target-branch`.

Non-interactive migration:

```bash
python3.11 bootstrap.py migrate \
  --gitverse-url https://gitverse.example/service.git \
  --bitbucket-url https://bitbucket.example/service.git \
  --branch develop \
  --corporate-branch develop-corp \
  --yes
```

`--branch` is the primary development branch used as the corporate branch base. `--corporate-branch` is optional; when omitted, interactive runs prompt for the branch name and offer `<primary>-corp` as the default. `--yes` confirms the generated plan for automation.

By default, clone operations use an isolated temporary workspace. `dry-run` and `sync` remove that temporary workspace after reporting. Pass `--workspace` when you want to keep the checkout for inspection.

Mode intent:

- `sync`: only GitVerse to Bitbucket branch synchronization.
- `migrate`: first-time corporate migration.
- `apply`: post-migration maintenance on an existing corporate branch.
- `update`: post-migration integration from GitVerse into an existing corporate branch.

Use `update`, not `sync`, when the goal is to update `develop-corp` or another corporate branch from GitVerse. IDE assistants must not manually run `git pull`, `git merge origin/<branch>`, or `git push bitbucket <source>:<target>` for this workflow.

## Expected Project Layout

The current GitVerse to Bitbucket migration stops unless the project already has exactly one application module matching `*-app`:

```text
pom.xml
<service>-app/
    pom.xml
    src/
```

The Skill never creates, renames, or moves application modules. If no `*-app` module exists, or more than one exists, migration is aborted.

## Out Of Scope

The Skill never modifies:

- business logic;
- REST API;
- DTOs;
- SQL;
- Liquibase;
- Flyway;
- application business configuration.

Requests that require those areas must be handled as service-owned changes outside this Skill.

## Architecture

```text
bootstrap.py              CLI and orchestration only
plugin_base.py            plugin interface and migration context
plugin_registry.py        dynamic plugin loading
planner.py                execution plan and rollback-aware execution
standard_loader.py        standards configuration loading
platform_version.py       project and latest standard version support
plugins/                  migration plugins
standards/                corporate standards and plugin registration
corporate-reference/      Maven golden reference files
templates/                non-Maven generated resources
references/               operator and maintainer guidance
tests/                    standard-library unit tests
```

## Migration Flow

1. Clone GitVerse.
2. Synchronize all GitVerse branches to Bitbucket using explicit refs.
3. Ask for the primary development branch.
4. Ask for the corporate branch name.
5. Validate project structure.
6. Verify an existing single `*-app` application module.
7. Abort if validation fails.
8. Generate the migration plan.
9. Ask for confirmation.
10. Execute migration plugins.

## Update Flow

1. Validate `--project` as an existing local Git repository.
2. Fetch GitVerse remote, normally `origin`.
3. Fetch Bitbucket remote, normally `bitbucket`.
4. Determine GitVerse source branch candidates.
5. Determine existing local and Bitbucket target branches.
6. Ask for the target branch if omitted.
7. Ask for the source branch if omitted, showing commit counts relative to the target.
8. Show the update plan.
9. Ask for confirmation unless `--yes`.
10. Checkout the existing target branch from Bitbucket.
11. Merge the selected GitVerse source branch.
12. Stop on conflicts and print recovery commands.
13. Run only requested post-merge tasks after a clean merge.
14. Commit and push only when requested.

## Plugin Architecture

Every plugin implements:

- `validate(context)`;
- `plan(context)`;
- `execute(context, dry_run=False)`;
- `rollback(context)`.

Current plugins:

- `plugins/git.py`
- `plugins/root_pom.py`
- `plugins/app_pom.py`
- `plugins/distributive.py`
- `plugins/cleanup.py`
- `plugins/logger.py`
- `plugins/finalize.py`

Plugins are registered in `standards/plugins.yaml`. Adding a migration requires one new plugin and one registration entry.

Plugin modules must live under `plugins.*`. This prevents standards configuration from importing arbitrary Python modules.

## Configuration-Driven Standards

Corporate standards live in:

- `standards/platform.yaml`
- `standards/dependencies.yaml`
- `standards/annotation-processors.yaml`
- `standards/maven-reference-mapping.yaml`
- `standards/cleanup.yaml`
- `standards/migration-rules.yaml`

These files are JSON-compatible YAML and are loaded with the Python standard library. Future changes to Maven placeholder defaults, cleanup targets, branch suffixes, or platform versions should be made in these files first.

Required standards keys are validated at startup so broken configuration fails with a readable error before any migration runs.

## Maven And Distributive Generation

Maven migration is golden-reference driven. Assistants and operators must run `bootstrap.py`; they must not manually reconstruct root POMs, app POMs, or distributive files.

Root POM migration:

- renders `pom.xml` from `corporate-reference/root-pom.xml`;
- replaces only supported placeholders;
- does not preserve arbitrary old root POM build, repository, profile, or dependency-management sections.

App POM migration:

- renders `<app-module>/pom.xml` from `corporate-reference/app-pom.xml`;
- replaces only supported placeholders;
- merges original source business dependencies into the golden app POM;
- does not merge arbitrary old app plugins, profiles, repositories, or build sections.

Distributive generation:

- validates `corporate-reference/distributive-pom.xml` before use;
- copies `corporate-reference/distributive-pom.xml` and `corporate-reference/distributive.xml`;
- replaces only approved placeholders;
- never simplifies or rewrites template XML structure.

## Platform Versioning

The latest platform standard is configured in `standards/platform.yaml`.

Current latest standard:

```text
Corporate Platform Standard 2026.06
```

Analyze mode reports the detected project standard version and latest standard version. The migration writes `.corp-platform-version` after successful execution.

## Rollback

Rollback is best effort. On failure after execution starts, the framework asks executed plugins to roll back in reverse order.

The Git plugin attempts to:

- restore the local working tree;
- delete the local corporate branch when it was created by the workflow;
- delete the remote corporate branch when it was created by the workflow and permissions allow.
- remove the temporary clone when it was created by the workflow.

Limitations:

- the original pushed branch is not deleted automatically;
- synchronized non-corporate branches are not deleted automatically;
- remote branch deletion may fail due to permissions or branch protection;
- explicit `--workspace` checkouts are left in place for inspection.

## Formatting Notes

Root and distributive Maven files are raw golden-reference renders with placeholder replacement only. App POM generation parses XML only to append missing business dependencies from the source app POM.

Java logger migration preserves logging statements, adds `Slf4j` to the normal import block, keeps static imports separate, and avoids duplicate annotations or imports.

## Troubleshooting

`Project validation failed`: verify the expected Maven layout exists and both POM files are valid XML.

`No remote branches were found`: verify the GitVerse URL and repository permissions.

`Clone destination is not empty`: pass a clean `--workspace` or remove the previous temporary checkout.

`Migration requires confirmation`: rerun interactively or pass `--yes` after reviewing the plan.

`Git command failed`: read the Git message in the error. Common causes are missing credentials, branch protection, or a Bitbucket URL typo.

`Unable to render distributive pom`: ensure the root POM has resolvable `groupId`, `artifactId`, and `version`.

`Provided distributive POM reference is invalid or not a distributive module POM`: replace `corporate-reference/distributive-pom.xml` with the approved corporate distributive POM reference.

## Verification

Run before publishing:

```bash
python3.11 -m unittest discover -s tests
python3.11 -m py_compile bootstrap.py config.py git_client.py validation.py cleanup.py report.py standard_loader.py plugin_base.py plugin_registry.py planner.py platform_version.py plugins/*.py migrators/*.py utils/*.py
```
