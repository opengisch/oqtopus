import logging

try:
    from qgis.gui import QgsFileWidget
except ImportError:
    QgsFileWidget = None

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QWidget,
)

from ..libs.pum import ParameterDefinition, ParameterType

logger = logging.getLogger(__name__)


class ParameterWidget(QWidget):
    def __init__(self, parameter_definition: ParameterDefinition, parent):
        QWidget.__init__(self, parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)
        self.value = None

        # Get the parameter type value (handle both enum and string cases)
        # This is needed because during plugin reload, enums can become strings
        param_type = parameter_definition.type
        if isinstance(param_type, ParameterType):
            param_type_value = param_type.value
        elif isinstance(param_type, str):
            # Handle string representations like "ParameterType.INTEGER" or "integer"
            param_type_value = (
                param_type.split(".")[-1].lower() if "." in param_type else param_type.lower()
            )
        else:
            param_type_value = str(param_type).split(".")[-1].lower()

        tooltip = parameter_definition.description or ""

        if param_type_value != "boolean":
            label = QLabel(parameter_definition.name, self)
            label.setToolTip(tooltip)
            self.layout.addWidget(label)

        if param_type_value == "boolean":
            self.widget = QCheckBox(parameter_definition.name, self)
            self.widget.setToolTip(tooltip)
            if parameter_definition.default is not None:
                self.widget.setChecked(parameter_definition.default)
            self.layout.addWidget(self.widget)
            self.layout.addStretch()
            self.value = lambda: self.widget.isChecked()
        elif param_type_value in ("decimal", "integer", "text"):
            if parameter_definition.values:
                self.widget = QComboBox(self)
                self.widget.setToolTip(tooltip)
                for v in parameter_definition.values:
                    self.widget.addItem(str(v), v)
                if parameter_definition.default is not None:
                    idx = self.widget.findData(parameter_definition.default)
                    if idx >= 0:
                        self.widget.setCurrentIndex(idx)
                self.layout.addWidget(self.widget)
                self.layout.addStretch()
                if param_type_value == "integer":
                    self.value = lambda: int(self.widget.currentData())
                elif param_type_value == "decimal":
                    self.value = lambda: float(self.widget.currentData())
                else:
                    self.value = lambda: self.widget.currentData()
            else:
                self.widget = QLineEdit(self)
                self.widget.setToolTip(tooltip)
                if parameter_definition.default is not None:
                    self.widget.setPlaceholderText(str(parameter_definition.default))
                self.layout.addWidget(self.widget)
                if param_type_value == "integer":
                    self.value = lambda: int(self.widget.text() or self.widget.placeholderText())
                elif param_type_value == "decimal":
                    self.value = lambda: float(self.widget.text() or self.widget.placeholderText())
                else:
                    self.value = lambda: self.widget.text() or self.widget.placeholderText()
        elif param_type_value == "path":
            if QgsFileWidget is not None:
                self.widget = QgsFileWidget(self)
                self.widget.setToolTip(tooltip)
                self.widget.setStorageMode(QgsFileWidget.StorageMode.GetFile)
                if parameter_definition.default is not None:
                    self.widget.setFilePath(str(parameter_definition.default))
                self.layout.addWidget(self.widget)
                self.value = lambda: self.widget.filePath()
            else:
                self.widget = QLineEdit(self)
                self.widget.setToolTip(tooltip)
                if parameter_definition.default is not None:
                    self.widget.setText(str(parameter_definition.default))
                self.layout.addWidget(self.widget)
                self.value = lambda: self.widget.text()
        else:
            raise ValueError(
                f"Unknown parameter type '{parameter_definition.type}' "
                f"(normalized to '{param_type_value}')"
            )
