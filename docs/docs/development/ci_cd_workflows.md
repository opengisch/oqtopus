# CI/CD Workflows

oQtopus provides reusable GitHub Actions workflows that module repositories can use to standardize their CI/CD pipelines. These workflows handle common tasks like plugin packaging, datamodel dumps, project translations, and changelog validation.

## Available workflows

All reusable workflows are defined in the [opengisch/oqtopus](https://github.com/opengisch/oqtopus) repository under `.github/workflows/`.

### Plugin package and release

**Workflow:** `reusable-plugin-package.yml`

Packages a QGIS plugin using [qgis-plugin-ci](https://github.com/opengisch/qgis-plugin-ci), uploads build artifacts on PRs, posts a download comment, and optionally releases to GitHub and/or [plugins.qgis.org](https://plugins.qgis.org).

```yaml
jobs:
  plugin-package:
    uses: opengisch/oqtopus/.github/workflows/reusable-plugin-package.yml@main
    with:
      plugin_name: teksi_wastewater
      release_tag: ${{ inputs.release_tag }}
      pre_package_commands: |
        ./plugin/scripts/package-pip-packages.sh
        ./plugin/scripts/download-interlis-libs.sh
      asset_paths: |
        plugin/teksi_wastewater/libs
        plugin/teksi_wastewater/interlis/bin
    secrets: inherit
```

#### Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `plugin_name` | yes | | Plugin directory/package name (e.g., `oqtopus`, `teksi_wastewater`) |
| `release_tag` | no | `''` | Release tag version. Empty for dev builds (uses `0.0.0`) |
| `pre_package_commands` | no | `''` | Shell commands to run before packaging (e.g., bundling dependencies) |
| `asset_paths` | no | `''` | Newline-separated list of extra asset paths for `qgis-plugin-ci --asset-path` |
| `release_to_qgis_org` | no | `false` | Whether to also release to plugins.qgis.org |
| `upload_to_github_release` | no | `true` | Whether to upload the plugin zip to the GitHub Release |
| `github_release_asset_label` | no | `oqtopus.plugin` | Label for the GitHub Release asset |

#### Secrets

| Secret | Required | Description |
|---|---|---|
| `TX_TOKEN` | no | Transifex API token for translations |
| `QGIS_ORG_TOKEN` | no | Token for publishing to plugins.qgis.org |

#### Behavior

- On **pull requests**: packages with version `0.0.0` and posts a sticky comment with a download link.
- On **push to main**: packages and pushes translation sources to Transifex.
- On **release** (when `release_tag` is set): packages and uploads to GitHub Release and optionally to plugins.qgis.org.

---

### Datamodel dumps and documentation

**Workflow:** `reusable-datamodel-dumps.yml`

Creates database dumps (custom + plain SQL) and generates [SchemaSpy](https://schemaspy.org/) documentation for the datamodel. Uses Docker Compose with PUM to install the datamodel.

```yaml
jobs:
  datamodel-dumps:
    uses: opengisch/oqtopus/.github/workflows/reusable-datamodel-dumps.yml@main
    with:
      pgservice: pg_signalo
      db_name: signalo
      demo_data: Lausanne
      compose_project_name: signalo
      release_tag: ${{ inputs.release_tag }}
    secrets: inherit
```

#### Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `pgservice` | yes | | PostgreSQL service name (e.g., `pg_signalo`, `pg_tww`) |
| `db_name` | yes | | Database name (e.g., `signalo`, `tww`) |
| `demo_data` | yes | | Demo data name (e.g., `Lausanne`, `Aletsch`) |
| `compose_project_name` | no | `db_name` | Docker Compose project name |
| `release_tag` | no | `''` | Release tag to upload dumps as GitHub Release assets |
| `pum_install_params` | no | `-p SRID 2056` | Additional parameters for the PUM install command |

#### Prerequisites

The calling repository must provide:

- A `docker-compose.yml` with `db`, `pum`, and `schemaspy` services (the `schemaspy` service activated via `COMPOSE_PROFILES=schemaspy`)
- An `.env.example` file
- A `datamodel/` directory with PUM configuration

#### Artifacts produced

| Artifact | Description |
|---|---|
| `datamodel-dumps` | Database dumps in custom and plain SQL formats |
| `datamodel-schemaspy` | SchemaSpy HTML documentation |

On release, both are zipped and uploaded to the GitHub Release.

---

### Project translation and packaging

**Workflow:** `reusable-project-translation-package.yml`

Translates a QGIS project file via Transifex, creates dev/prod variants with different `PGSERVICE` names, and packages everything for release.

```yaml
jobs:
  project-translation-package:
    uses: opengisch/oqtopus/.github/workflows/reusable-project-translation-package.yml@main
    with:
      module_name: signalo
      qgs_project_file: signalo
      qgs_project_title: Signalo
      pgservice: pg_signalo
      db_name: signalo
      release_tag: ${{ inputs.release_tag }}
    secrets: inherit
```

#### Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `module_name` | yes | | Module name (e.g., `signalo`, `tww`) |
| `qgs_project_file` | yes | | QGS project file basename without extension (e.g., `signalo`, `teksi_wastewater`) |
| `qgs_project_title` | yes | | QGS project display title (e.g., `Signalo`, `TWW`) |
| `pgservice` | yes | | PostgreSQL service name (e.g., `pg_signalo`, `pg_tww`) |
| `db_name` | yes | | Database name (e.g., `signalo`, `tww`) |
| `release_tag` | no | `''` | Release tag to upload translations as GitHub Release asset |
| `pum_install_params` | no | `-p SRID 2056` | Additional parameters for the PUM install command |

#### Secrets

| Secret | Required | Description |
|---|---|---|
| `TX_TOKEN` | no | Transifex API token for translations |

#### Prerequisites

The calling repository must provide:

- A `docker-compose.yml` with `db`, `pum`, and `qgis` services (the `qgis` service activated via `COMPOSE_PROFILES=qgis`)
- A `project/` directory containing:
    - The `.qgs` project file
    - A `.tx/` Transifex configuration directory
    - `scripts/project-translation-create-source.py`
    - `scripts/project-translation-compile.sh`

#### Behavior

- On **push to main**: pushes translation sources to Transifex.
- On **PR / schedule / dispatch**: compiles translations and uploads an artifact.
- On **release** (when `release_tag` is set): updates the project version, creates the package, and uploads to the GitHub Release with the `oqtopus.project` label.

---

### Datamodel version check

**Workflow:** `reusable-datamodel-version-check.yml`

Validates that changelogs in `datamodel/changelogs/` are not modified in directories corresponding to already-released versions. This prevents accidental changes to stable migration scripts.

```yaml
jobs:
  version-tests:
    uses: opengisch/oqtopus/.github/workflows/reusable-datamodel-version-check.yml@main
    secrets: inherit
```

This workflow has no inputs. It runs only on pull requests and uses the `GITHUB_TOKEN` secret to query the latest release tag.

---

## Typical release workflow

Module repositories typically define a release workflow that calls the reusable workflows when a GitHub Release is published:

```yaml
name: 🚀 Release

on:
  release:
    types: [published]

jobs:
  datamodel-dumps:
    uses: ./.github/workflows/datamodel-dumps-documentation.yml
    with:
      release_tag: ${{ github.event.release.tag_name }}

  plugin-package:
    uses: ./.github/workflows/plugin-package.yml
    with:
      release_tag: ${{ github.event.release.tag_name }}
    secrets: inherit

  project-translations:
    uses: ./.github/workflows/project-translation-package.yml
    with:
      release_tag: ${{ github.event.release.tag_name }}
    secrets: inherit
```

Each of these local wrapper workflows in turn calls the corresponding oqtopus reusable workflow, passing module-specific parameters.

## Examples

See these repositories for real-world usage:

- [opengisch/signalo](https://github.com/opengisch/signalo/tree/main/.github/workflows) — datamodel dumps, project translations, version check
- [teksi/wastewater](https://github.com/teksi/wastewater/tree/main/.github/workflows) — all four workflows
