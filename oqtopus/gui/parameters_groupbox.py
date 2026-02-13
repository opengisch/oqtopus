import logging

from qgis.PyQt.QtWidgets import (
    QGroupBox,
    QSizePolicy,
)

from ..libs.pum import ParameterDefinition
from .parameter_widget import ParameterWidget

logger = logging.getLogger(__name__)


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
