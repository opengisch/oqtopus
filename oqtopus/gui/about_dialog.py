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
import subprocess

from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtGui import QFont, QPixmap
from qgis.PyQt.QtWidgets import QDialog, QLabel

from ..utils.plugin_utils import PluginUtils

DIALOG_UI = PluginUtils.get_ui_class("about_dialog.ui")


def _git_version(path: str) -> str | None:
    """If *path* lives inside a git repo, return ``git describe --tags``."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _dist_info_version(libs_dir: str, dist_name: str) -> str | None:
    """Return version from the ``<dist_name>-*.dist-info/METADATA`` in *libs_dir*."""
    prefix = f"{dist_name}-"
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
    return None


def get_library_version(name: str) -> dict[str, str]:
    """Return version info for a bundled library.

    Looks for a ``<name>-*.dist-info`` directory under ``libs/`` and
    extracts the version.  When the library is symlinked to a git repo
    (dev mode), ``git describe --tags`` is used instead.

    Returns a dict with keys ``name``, ``version``, and ``path``.
    """
    libs_dir = os.path.join(PluginUtils.plugin_root_path(), "libs")
    pkg_path = os.path.join(libs_dir, name)

    # Dev mode: if the package is a symlink into a git repo, use git
    version = None
    real_path = os.path.realpath(pkg_path)
    if real_path != os.path.abspath(pkg_path) and os.path.isdir(real_path):
        version = _git_version(real_path)

    # Otherwise read from dist-info
    if version is None and os.path.isdir(libs_dir):
        version = _dist_info_version(libs_dir, name)

    return {"name": name, "version": version or "?", "path": pkg_path}


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
        lib_versions = [
            get_library_version("pgserviceparser"),
            get_library_version("pum"),
        ]

        bold_font = QFont()
        bold_font.setBold(True)

        grid = self.gridLayout_2
        next_row = grid.rowCount()

        for i, lib in enumerate(lib_versions):
            label = QLabel(f"{lib['name']} version:")
            label.setFont(bold_font)
            value = QLabel(lib["version"])
            value.setToolTip(lib["path"])
            grid.addWidget(label, next_row + i, 0)
            grid.addWidget(value, next_row + i, 1)
