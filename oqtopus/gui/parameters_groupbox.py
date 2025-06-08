import logging

from pum import ParameterDefinition, ParameterType
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QWidget,
)

logger = logging.getLogger(__name__)


class ParameterWidget(QWidget):
    def __init__(self, parameter_definition: ParameterDefinition, parent):
        QWidget.__init__(self, parent)
        self.layout = QHBoxLayout(self)
        self.setLayout(self.layout)
        self.value = None

        if parameter_definition.type != ParameterType.BOOLEAN:
            self.layout.addWidget(QLabel(parameter_definition.name, self))

        if parameter_definition.type == ParameterType.BOOLEAN:
            self.widget = QCheckBox(parameter_definition.name, self)
            self.widget.setChecked(parameter_definition.default)
            self.layout.addWidget(self.widget)
            self.value = lambda: self.widget.isChecked()
        elif parameter_definition.type in (
            ParameterType.DECIMAL,
            ParameterType.INTEGER,
            ParameterType.TEXT,
        ):
            self.widget = QLineEdit(self)
            self.widget.setPlaceholderText(parameter_definition.default.as_string())
            self.layout.addWidget(self.widget)
            if parameter_definition.type == ParameterType.TEXT:
                self.value = lambda: self.widget.text()
            else:
                self.value = lambda: self.widget.value()


class ParametersGroupBox(QGroupBox):
    def __init__(self, parent):
        QGroupBox.__init__(self, parent)
        self.layout = QGridLayout(self)
        self.setLayout(self.layout)
        self.parameter_widgets = {}

    def setParameters(self, parameters: list[ParameterDefinition]):
        logger.info("Setting parameters in ParametersGroupBox (%s)", len(parameters))
        self.clean()
        self.parameters = parameters
        # Remove all widgets from the parameters_group_box layout
        for parameter in parameters:
            pw = ParameterWidget(parameter, self)
            self.layout.addWidget(pw)
            self.parameter_widgets[parameter.name] = pw

    def parameters_values(self):
        values = {}
        for parameter in self.parameters:
            values[parameter.name] = self.parameter_widgets[parameter.name].value()
        return values

    def clean(self):
        for widget in self.parameter_widgets:
            widget.deleteLater()
        self.parameter_widgets = {}
