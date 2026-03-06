Here come all GitHub CI actions workflows

## Reusable workflows

The following reusable workflows are available for oqtopus-based projects (e.g., [signalo](https://github.com/opengisch/signalo), [wastewater](https://github.com/teksi/wastewater)):

| Workflow | Description |
|---|---|
| `reusable-plugin-package.yml` | Packages a QGIS plugin with qgis-plugin-ci, uploads artifact, comments on PRs, and optionally releases to GitHub and/or plugins.qgis.org |
| `reusable-datamodel-dumps.yml` | Creates database dumps and schemaspy documentation from a datamodel using docker compose + pum |
| `reusable-project-translation-package.yml` | Updates QGIS project translations via Transifex, creates dev/prod project packages, and uploads to GitHub Release |
| `reusable-datamodel-version-check.yml` | Validates that changelogs are not modified in already-released datamodel versions (runs on PRs only) |

### Usage

Reference these workflows from your repository:

```yaml
jobs:
  my-job:
    uses: opengisch/oqtopus/.github/workflows/reusable-plugin-package.yml@main
    with:
      plugin_name: my_plugin
    secrets: inherit
```

See each workflow file for the full list of inputs and secrets.
