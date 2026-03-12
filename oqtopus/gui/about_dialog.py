# -----------------------------------------------------------
#
# Profile
# Copyright (C) 2012  Patrice Verchere
# -----------------------------------------------------------
#
# licensed under the terms of GNU GPL 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, print to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# ---------------------------------------------------------------------


import os

from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtGui import QFont, QPixmap
from qgis.PyQt.QtWidgets import QDialog, QLabel

from ..utils.plugin_utils import PluginUtils

DIALOG_UI = PluginUtils.get_ui_class("about_dialog.ui")


def _lib_version(package_name: str, package_path: str) -> str:
    """Return the version of a bundled library.

    Tries ``importlib.metadata`` first, then falls back to scanning for a
    ``<package>-*.dist-info/METADATA`` file next to *package_path*.
    """
    try:
        from importlib.metadata import version

        return version(package_name)
    except Exception:
        pass

    # Fallback: look for a dist-info directory next to the package
    libs_dir = os.path.dirname(package_path)
    prefix = f"{package_name}-"
    for entry in os.listdir(libs_dir):
        if entry.startswith(prefix) and entry.endswith(".dist-info"):
            metadata_file = os.path.join(libs_dir, entry, "METADATA")
            if os.path.isfile(metadata_file):
                with open(metadata_file) as f:
                    for line in f:
                        if line.startswith("Version:"):
                            return line.split(":", 1)[1].strip()
            # Extract from directory name as last resort
            return entry[len(prefix) : -len(".dist-info")]
    return "?"


class AboutDialog(QDialog, DIALOG_UI):
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setupUi(self)

        metadata_file_path = PluginUtils.get_metadata_file_path()

        ini_text = QSettings(metadata_file_path, QSettings.Format.IniFormat)
        version = ini_text.value("version")
        name = ini_text.value("name")
        description = "".join(ini_text.value("description"))
        about = " ".join(ini_text.value("about"))
        qgisMinimumVersion = ini_text.value("qgisMinimumVersion")

        self.setWindowTitle(f"{name} - {version}")
        self.titleLabel.setText(self.windowTitle())
        self.descriptionLabel.setText(description)
        self.aboutLabel.setText(about)
        self.qgisMinimumVersionLabel.setText(qgisMinimumVersion)

        scaled_logo = QPixmap(PluginUtils.get_plugin_icon_path("oqtopus-logo.png")).scaled(
            254,
            254,
            aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
            transformMode=Qt.TransformationMode.SmoothTransformation,
        )
        self.iconLabel.setPixmap(scaled_logo)

        # --- Library versions ---
        oqtopus_path = PluginUtils.plugin_root_path()
        oqtopus_version = _lib_version("oqtopus", oqtopus_path)

        from ..libs import pum as _pum_pkg

        pum_path = os.path.dirname(_pum_pkg.__file__)
        pum_version = _lib_version("pum", pum_path)

        bold_font = QFont()
        bold_font.setBold(True)

        grid = self.gridLayout_2
        next_row = grid.rowCount()

        oqtopus_label = QLabel("oQtopus version:")
        oqtopus_label.setFont(bold_font)
        oqtopus_value = QLabel(oqtopus_version)
        oqtopus_value.setToolTip(oqtopus_path)
        grid.addWidget(oqtopus_label, next_row, 0)
        grid.addWidget(oqtopus_value, next_row, 1)

        pum_label = QLabel("PUM version:")
        pum_label.setFont(bold_font)
        pum_value = QLabel(pum_version)
        pum_value.setToolTip(pum_path)
        grid.addWidget(pum_label, next_row + 1, 0)
        grid.addWidget(pum_value, next_row + 1, 1)
