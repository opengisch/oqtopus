import logging

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
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
        elif param_type_value in ("decimal", "integer", "text", "path"):
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
        else:
            raise ValueError(
                f"Unknown parameter type '{parameter_definition.type}' "
                f"(normalized to '{param_type_value}')"
            )


class ParametersGroupBox(QGroupBox):
    def __init__(self, parent):
        QGroupBox.__init__(self, parent)
        self.parameter_widgets = {}
        self.parameters = []
        # Don't expand vertically beyond what the contents need
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

    def setParameters(self, parameters: list[ParameterDefinition]):
        logger.debug(f"Setting parameters in ParametersGroupBox ({len(parameters)})")
        self.clean()
        self.parameters = parameters

        if not parameters:
            self.setVisible(False)
            return

        self.setVisible(True)

        for parameter in parameters:
            pw = ParameterWidget(parameter, self)
            self.layout().addWidget(pw)
            self.parameter_widgets[parameter.name] = pw

    def parameters_values(self):
        values = {}
        for parameter in self.parameters:
            values[parameter.name] = self.parameter_widgets[parameter.name].value()
        return values

    def setParametersEnabled(self, enabled: bool):
        """Enable or disable the parameter widgets without affecting the scroll area."""
        for pw in self.parameter_widgets.values():
            pw.setEnabled(enabled)

    def clean(self):
        for widget in self.parameter_widgets.values():
            widget.deleteLater()
        self.parameter_widgets = {}
