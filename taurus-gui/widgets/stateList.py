# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 3
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

__author__ = "Sergi Blanch-Torne"
__email__ = "sblanch@cells.es"
__copyright__ = "Copyright 2017 CELLS/Alba synchrotron"
__license__ = "GPLv3+"
__status__ = "development"

import os
from taurus import Attribute, Device
from taurus.external.qt import Qt, QtGui
from taurus.qt.qtgui.container import TaurusWidget
from taurus.qt.qtgui.display import TaurusLed, TaurusLabel
from taurus.qt.qtgui.input import TaurusValueLineEdit
from taurus.qt.qtgui.util.ui import UILoadable


@UILoadable(with_ui="ui")
class StateList(TaurusWidget):
    def __init__(self, parent=None, name=None, designMode=False):
        super(StateList, self).__init__()
        basePath = os.path.dirname(__file__)
        if len(basePath) == 0:
            basePath = '.'
        self.loadUi(filename="stateList.ui",
                    path=basePath+"/ui")

    _model = None

    def getModel(self):
        return self._model

    def setModel(self, model):
        if model != self._model and len(model) == 2:
            try:
                self.info("New model: %r" % (model))
                self._setAttributes(model[0], model[1])
                self._model = model
            except Exception as e:
                self.error("New model not valid: %s" % (e))
                self._setAttributes(self._model[0], self._model[1])
        else:
            self.warning("Set the same model than has")

    def _setAttributes(self, model, state):
        device = Device(model)
        try:
            device['%sDevices' % (state)].value
        except:
            raise Exception("model %s doesn't monitor %s state" % (model, state))
        self.ui.stateLabel.setText(state)
        self.ui.number.setModel("%s/%sDevices" % (model, state))
        self.ui.devList.setModel("%s/%sDevicesList" % (model, state))
        self._adjustTable()
    
    def _adjustTable(self):
        self.ui.devList._rwModeCB.hide()
        self.ui.devList._label.hide()
        tableView = self.ui.devList._tableView
        tableView.horizontalHeader().setResizeMode(Qt.QHeaderView.Stretch)
        tableView.resizeColumnsToContents()
