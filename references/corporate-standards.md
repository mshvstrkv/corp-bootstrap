# Corporate Standards

Use this file when reviewing or changing what v2 enforces.

## Source Of Truth

Corporate standards are configuration-driven:

- `standards/platform.yaml`: platform version, default app module fallback, branch suffix, commit message.
- `standards/plugins.yaml`: enabled plugins and execution order.
- `standards/dependencies.yaml`: required dependencies and exclusions.
- `standards/annotation-processors.yaml`: compiler annotation processors.
- `standards/maven-template-values.yaml`: Maven golden-reference placeholder defaults.
- `standards/cleanup.yaml`: files and directories removed during cleanup.
- `standards/migration-rules.yaml`: root POM, distributive, logger, and out-of-scope rules.

Do not hardcode corporate standards in Python. If a standard can be expressed as data, it belongs under `standards/`.

Maven and distributive generation must come from `corporate-reference/` golden files plus placeholder config. Do not improvise POM structure in Python or Skill instructions.

## Current Platform Standard

```text
Corporate Platform Standard 2026.06
```

Analyze mode reports both detected project version and latest version. Migration writes `.corp-platform-version` after successful execution.

## Current Supported Service Shape

```text
pom.xml
<service>-app/
    pom.xml
    src/
```

The repository must already contain exactly one `*-app` module. The Skill never creates the module, moves source files, or converts a flat project into a modular project. `standards/platform.yaml` contains only a fallback app module value for backward-compatible APIs.

## Out Of Scope

The Skill never modifies:

- business logic;
- REST API;
- DTOs;
- SQL;
- Liquibase;
- Flyway;
- application business configuration.

## Adding Or Changing Standards

For dependency, Maven plugin, cleanup, logger, distributive, branch, or version changes:

1. edit the relevant file in `standards/`;
2. update `corporate-reference/` only when approved Maven reference content changes;
3. update golden-file fixtures under `tests/fixtures/maven/expected/`;
4. update tests to prove idempotency and analysis output;
5. update `README.md`, canonical `SKILL.md`, and any lowercase `skill.md` mirror only when operator behavior changes.

Do not modify existing plugin code for data-only standard changes.
