# Installation

oQtopus can be installed either as a **QGIS plugin** or as a **standalone** Python application.

## QGIS Plugin

### Prerequisites

Make sure the following Python packages are available in your QGIS environment:

- `psycopg` (PostgreSQL driver)
- `pydantic`

`pip` must be available in that same environment too. Besides installing the packages
above, it might be used by PUM, which calls `python -m pip` the first time a module is
loaded in order to install the Python dependencies that a module declares. Module
initialization fails when pip is missing. 

!!! warning "Windows"

    Note that pip is shipped neither by the QGIS installer nor by OSGeo4W installer.
    
    In OSGeo4W installer, it can be installed by selecting the `python3-pip` package or
    in the OSGeo4W Shell with: `python -m ensurepip --upgrade`

    On 3.x installation of QGIS, pydantic or psycopg might be missing. You can install them
    from the OSGeo4W Shell with `pip install --upgrade pydantic psycopg`

### Install the plugin

1. Open **QGIS ≥ 3.40** (LTR).
2. Go to **Extensions → Manage and Install Plugins → Settings** and enable **experimental plugins**.
3. Search for **oQtopus** and click **Install**.

## Standalone Application

### Install

```bash
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
