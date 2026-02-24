# Installation

oQtopus can be installed either as a **QGIS plugin** or as a **standalone** Python application.

## QGIS Plugin

### Prerequisites

!!! warning "Windows"

    On Windows, the QGIS installation does not ship all required Python libraries.
    Open the **OSGeo4W Shell** and run:

    ```
    pip install --upgrade pum pydantic psycopg
    ```

Make sure the following Python packages are available in your QGIS environment:

- `psycopg` (PostgreSQL driver)
- `pydantic`
- `pum`
- `pirogue`

### Install the plugin

1. Open **QGIS ≥ 3.40** (LTR).
2. Go to **Extensions → Manage and Install Plugins → Settings** and enable **experimental plugins**.
3. Search for **oQtopus** and click **Install**.

## Standalone Application

### Install

```bash
pip install pyqt6          # PyQt5 is not supported in standalone mode
pip install oqtopus
```

### Run

```bash
python3 -m oqtopus.oqtopus
```

!!! note

    In standalone mode the path to `default_config.yaml` is resolved from the
    installed package directory. To add custom modules, locate the file inside the
    pip installation and edit it (see [Adding Modules](adding_modules.md)).
