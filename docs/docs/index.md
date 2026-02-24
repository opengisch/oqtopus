
![oqtopus_logo](./assets/images/oqtopus.png#only-light){: style="width:400px"}
![oqtopus_logo](./assets/images/oqtopus.png#only-dark){: style="width:400px"}

# oQtopus

oQtopus is a QGIS module manager that helps you **deploy**, **manage** and **upgrade** your QGIS projects, plugins and associated PostgreSQL / PostGIS datamodel implementations.

Datamodel installation, upgrade and migration are powered by the PostgreSQL Upgrade Manager [PUM](https://github.com/opengisch/pum/).

oQtopus can be used as a **QGIS plugin** or as a **standalone** Python application.

## Features

- **Module installation** — install a PostgreSQL/PostGIS datamodel from a versioned GitHub release in a single click.
- **Module upgrade** — upgrade an installed datamodel to a newer version (including pre-releases and development branches).
- **Role management** — inspect, create, grant and revoke PostgreSQL roles defined by the module.
- **Project deployment** — download and install the QGIS project template associated with a module, with automatic PG service injection.
- **Plugin deployment** — install or export the companion QGIS plugin shipped with a module release.
- **Database utilities** — create or duplicate PostgreSQL databases directly from the GUI.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  oQtopus (QGIS plugin or standalone)            │
│  ┌──────────────┐  ┌────────────────────────┐   │
│  │ Module       │  │ Database Connection     │   │
│  │ Selection    │  │ (PG Service)            │   │
│  └──────┬───────┘  └───────────┬────────────┘   │
│         │                      │                 │
│  ┌──────┴──────────────────────┴──────────────┐  │
│  │  Module  │  Project  │  Plugin             │  │
│  │  (PUM)   │  (.qgs)   │  (.zip)             │  │
│  └──────────┴───────────┴─────────────────────┘  │
└─────────────────────────────────────────────────┘
```

Each module is defined in a YAML configuration file and points to a GitHub repository containing a PUM datamodel, an optional QGIS project and an optional QGIS plugin.

## Links

- **Source code**: [github.com/opengisch/oqtopus](https://github.com/opengisch/oqtopus)
- **PUM documentation**: [opengisch.github.io/pum](https://opengisch.github.io/pum/)
- **Issue tracker**: [github.com/opengisch/oqtopus/issues](https://github.com/opengisch/oqtopus/issues)
