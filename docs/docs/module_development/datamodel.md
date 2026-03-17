# Datamodel

## Introduction

oQtopus downloads the source code from the configured repository and looks for a PUM configuration file at:

```
datamodel/.pum.yaml
```

This file defines the database schema, migration scripts, parameters, roles and more.
See the [PUM documentation](https://opengisch.github.io/pum/) for details.


## Demo data

Demo data should be provided as plain SQL content. You can define several demo data sets (see the [PUM demo data documentation](https://opengisch.github.io/pum/demo_data/)).

Demo data must be compatible with the latest version of the datamodel. When updating the datamodel on the repository, an automated test checks that the demo data is still compliant.

If the demo data becomes incompatible after introducing a datamodel change, the recommended approach is:

1. Install the previous version of the datamodel.
2. Load the demo data.
3. Run the upgrade to the latest version.
4. Dump the demo data as plain SQL.
5. Include the demo data in the code change request.
