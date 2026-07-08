# Maintainer Guide

Use this file when evolving `corp-bootstrap` as an internal platform framework.

## Compatibility Contract

Keep these stable:

- directory name `corp-bootstrap`;
- canonical `SKILL.md`, plus a lowercase `skill.md` mirror only in packaging environments that support both names;
- CLI entrypoint `bootstrap.py`;
- modes `analyze`, `dry-run`, `migrate`;
- arguments `--gitverse-url`, `--bitbucket-url`, `--branch`, `--corporate-branch`, `--workspace`, `--project`;
- branch suffix default `-corp`;
- commit message default `Corporate migration`;
- standard report step names where possible;
- Python standard-library-only implementation.

`--yes` is additive and exists for non-interactive confirmation.

`--branch` means primary development branch. It does not mean "only branch to synchronize".

## Plugin Contract

Each plugin must implement `MigrationPlugin`:

```python
validate(context) -> list[str]
plan(context) -> list[PlanItem]
execute(context, dry_run=False) -> OperationResult
rollback(context) -> OperationResult
```

Plugin rules:

- do not call other plugins directly;
- do not hardcode corporate standards;
- keep plugin modules under `plugins.*`;
- return idempotent results;
- keep rollback best effort and explicit about limitations;
- use `OperationResult` for user-facing reporting.

## Adding A New Migration

1. Add `plugins/<name>.py`.
2. Expose `create_plugin()`.
3. Add configuration under `standards/` if the plugin enforces corporate policy.
4. Register the plugin in `standards/plugins.yaml`.
5. Add tests.
6. Update docs only when developer behavior changes.

No existing plugin should require modification for a new independent migration.

## Maven Maintainer Contract

Maven migration must remain golden-reference driven:

- do not reconstruct POM files in Skill instructions or IDE assistant prompts;
- keep Maven golden references in `corporate-reference/root-pom.xml`, `corporate-reference/app-pom.xml`, `corporate-reference/distributive-pom.xml`, and `corporate-reference/distributive.xml`;
- keep Maven placeholder defaults in `standards/maven-template-values.yaml`;
- keep app POM dependency merging limited to source business dependencies;
- update golden-file fixtures whenever approved corporate Maven references change;
- fail fast when the distributive POM template is not a distributive module POM.

## Versioning

Platform versions are data:

- latest standard: `standards/platform.yaml`;
- detected project version: root POM property or `.corp-platform-version`;
- future upgrade commands should compare project version to latest and choose registered plugins.

Do not implement future upgrade behavior by branching inside existing plugins. Add new plugins or command modes.

## Idempotency Checklist

- no duplicate XML nodes;
- no duplicate Java imports or annotations;
- generated files are rewritten only when content differs;
- cleanup ignores absent paths;
- commits are skipped when there are no changes;
- repeated analysis produces the same report for the same tree.
- validation never creates application modules, moves source, or converts project structure.

## Rollback Checklist

- track created local and remote branches in `context.state`;
- restore local working tree when possible;
- delete remote corporate branch only when this run created it;
- do not delete the original branch automatically;
- do not delete synchronized non-corporate branches automatically;
- report rollback failures as warnings.
- never delete paths unless they are confirmed children of the migration workspace.

## Security Checklist

- use `subprocess.run` with argument lists, never `shell=True`;
- validate Git branch names with Git before checkout or push;
- push explicit `refs/heads/...` refspecs;
- synchronize every GitVerse remote branch before creating the corporate branch;
- redact URL credentials from Git diagnostics;
- sanitize repository-derived directory names;
- keep default clone workspaces isolated and temporary;
- restrict plugin registration to `plugins.*`;
- treat standards files as configuration, not executable code.

## Release Checklist

```bash
python3.11 -m unittest discover -s tests
python3.11 -m py_compile bootstrap.py config.py git_client.py validation.py cleanup.py report.py standard_loader.py plugin_base.py plugin_registry.py planner.py platform_version.py plugins/*.py migrators/*.py utils/*.py
```

Run one manual dry-run and one migration against a disposable repository before publishing a new platform standard to many teams.
