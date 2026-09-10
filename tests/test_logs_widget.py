"""Unit tests for the log view models.

Requires PyQt5 or PyQt6; QGIS is not needed (the standalone shim is used).
"""

import importlib
import sys

import pytest

# Install the fake ``qgis.PyQt`` modules before anything imports them. Written as
# a call rather than an import statement so that isort cannot sort it below the
# ``qgis`` imports, which would defeat it.
importlib.import_module("oqtopus._qgis_shim")

from qgis.PyQt.QtCore import QModelIndex, Qt  # noqa: E402
from qgis.PyQt.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

from oqtopus.gui.logs_widget import COLUMNS, LogFilterProxyModel, LogModel  # noqa: E402


def _log(level="INFO", module="mod", message="hello"):
    return {
        "Timestamp": "2026-09-10 12:00:00",
        "Level": level,
        "Module": module,
        "Message": message,
    }


@pytest.fixture()
def model():
    model = LogModel()
    for level in ("DEBUG", "INFO", "ERROR"):
        model.add_log(_log(level=level, message=f"{level} message"))
    return model


def test_root_counts(model):
    assert model.rowCount(QModelIndex()) == 3
    assert model.columnCount(QModelIndex()) == len(COLUMNS)
    # The parameterless call is what Python callers use.
    assert model.rowCount() == 3


def test_rows_have_no_children(model):
    """The model is flat: a row must not report itself as a parent of rows.

    Reporting the log count under every row makes the model an infinitely deep
    tree, which QSortFilterProxyModel and the accessibility bridge both walk.
    """
    first = model.index(0, 0, QModelIndex())
    assert first.isValid()
    assert model.rowCount(first) == 0
    assert model.columnCount(first) == 0
    assert not model.hasChildren(first)
    assert not model.index(0, 0, first).isValid()


def test_empty_model_has_no_rows():
    empty = LogModel()
    assert empty.rowCount(QModelIndex()) == 0
    assert not empty.index(0, 0, QModelIndex()).isValid()


def test_flags_on_the_root_index(model):
    """The root is not an item, so it carries no item flags."""
    assert model.flags(QModelIndex()) == Qt.ItemFlag.NoItemFlags
    assert model.flags(model.index(0, 0, QModelIndex())) & Qt.ItemFlag.ItemIsEnabled


def test_proxy_filters_without_recursing(model):
    proxy = LogFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.setLevelFilter("ERROR")
    assert proxy.rowCount(QModelIndex()) == 1
    assert proxy.data(proxy.index(0, 1, QModelIndex()), Qt.ItemDataRole.DisplayRole) == "ERROR"

    # No row of the filtered view claims children either.
    for row in range(proxy.rowCount(QModelIndex())):
        assert proxy.rowCount(proxy.index(row, 0, QModelIndex())) == 0
