# Getting Started

oQtopus is designed to deploy PostgreSQL modules managed by [pum](https://github.com/opengisch/pum/) along with a QGIS project and plugin.
It can be installed either as a QGIS plugin or as a standalone Python executable.

## oQtopus as a QGIS Plugin

### Installation

#### 🔧 Prerequisites (Mainly python packages)

> [!WARNING]
> On Windows, QGIS installation doesn't provide the necessary Python libraries yet.
> You need to install psycopg and pydantic using pip.

Before anything, you should check for these python packages to be available in your QGIS environment :

On windows start the osgeo4w shell and run following command :
```
pip install --upgrade pum pirogue pydantic psycopg
```

#### Install the Module management plugin

1. Run your QGIS (>=) 3.40 (LTR)
2. Under the extensions manager / parameters -> tick the experimental plugins

![image](https://github.com/user-attachments/assets/cad47237-2d3e-457c-8ce3-aaef31dc7254)

3. Search for `oQtopus` with a `Q` like `QGIS` and install the latest release

![image](https://github.com/user-attachments/assets/0438c435-efaf-477f-97c2-9d42968b760a)

### Download a module

In the `Module selection` box:

1. Launch the plugin
2. Select the desired module (ie. `TWW` and the version (ie. `2025.0.1rc2`))
3. Wait for the assests being downloaded

!!! note "Alternative versions"

    By default oQtopus lists versions listed in the releases list of the Github project.
    But it is also possible to install from a .zip archive of the source code.
    By selecting "Load development branches" in the versions combobox oQtopus will load
    additional installable versions for the main branch and all branches from open pull requests.


### Create or prepare the host database

In the `Database connection` box, you can either:

* Choose a defined PG Service for an existing database
* `...` Create an empty database and create the corresponding PG service
* `...` Duplicate an existing database


### Install the module

In the previous steps, you selected the module to be installed and defined the destination database.

In the `Module` tab:

* Tick if you want to create and grant roles. Attention, if the module users are not existing in the postgresql server, the installation of the module might fail.
* Tick if you want to install demo data and choose which demo dataset
* **advanced users**: specify advanced installation parameters in the `Parameters` box.
* Click `Install XXXXX`


## Get the projet

In the `Project` tab:

* Click `Install template project` and choose the project destination. The project is initialized with the defined service.
* If the langage setting are properly defined (QGIS local is defined and corresponding translation `.qm` file is existing. Ie. fr_CH and `module_name_fr_CH.qgs`), the project is translated in your langage.
* If a pg service is selected, all references in the project file are updated to use it.


## Install the module plugin

In the `Plugin` tab, you can install the module plugin (ie. TWW plugin). Direct install using the `Install` button is currently not implemented.

* Click `Copy ZIP to directory`
* In QGIS > Extension > Install and manage extension > Install from ZIP


## oQtopus as a standalone python executable

### Install module and requirements

``` bash
pip install pyqt6  # Or pyqt5 depending whats available on your system
pip install oqtopus
```

### Run the application

``` bash
python3 -m oqtopus.oqtopus
```

> [!WARNING]
> At the moment the path to `default_config.yaml`is hard coded in Oqtopus, if you need
> to change the config, for example for adding new modules, you will have to find
> the installation directory of the pip package to locate the file.
