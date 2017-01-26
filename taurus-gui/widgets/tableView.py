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
from taurus.external.qt import QtGui
from taurus.qt.qtgui.container import TaurusWidget
from taurus.qt.qtgui.display import TaurusLed, TaurusLabel
from taurus.qt.qtgui.input import TaurusValueLineEdit
from taurus.qt.qtgui.util.ui import UILoadable


@UILoadable(with_ui="ui")
class TableView(TaurusWidget):
    def __init__(self, parent=None, name=None, designMode=False):
        super(TableView, self).__init__()
        basePath = os.path.dirname(__file__)
        if len(basePath) == 0:
            basePath = '.'
        self.loadUi(filename="tableView.ui", path=basePath+"/ui")

    _model = None
    _extraColumns = []

    def getModel(self):
        return self._model

    def setModel(self, model):
        model = str(model)
        if model != self._model:
            try:
                self.debug("New model: %r" % (model))
                self._buildTable(model)
                self._model = model
            except Exception as e:
                self.error("New model not valid: %s" % (e))
                self._buildTable(self._model)
        else:
            self.warning("Set the same model than has")

    def _buildTable(self, devName):
        device = Device(devName)
        if self._rowCount() != 1:
            self.debug("clean rows")  # TODO
        try:  # taurus4
            values = device['DevicesList'].rvalue
        except:  # taurus3
            values = device['DevicesList'].value
        for i, monitored in enumerate(values):
            self._setRow(i+1, devName, monitored)
        # TODO: if the watchdog has an attrLst for this column add a button
        #       on the bottom of the current column to display the plot.

    def _rowCount(self):
        return self.ui.table.rowCount()

    def _setRow(self, row, watchdogName, monitoredName):
        self.debug("Build a row %d with device %s" % (row, monitoredName))
        name = QtGui.QLabel("%s" % (monitoredName), self)
        self.ui.table.addWidget(name, row, 0)
        stateLed = TaurusLed()
        stateLed.setModel("%s/%s\\State" % (watchdogName,
                                            monitoredName.replace('/', '\\')))
        self.ui.table.addWidget(stateLed, row, 1)
        self._setSubcolumns(row, watchdogName, monitoredName)

    def _setSubcolumns(self, row, watchdogName, monitoredName):
        self.debug("subcolumns for %s" % (watchdogName))
        device = Device(watchdogName)
        try:  # taurus4
            value = device['ExtraAttrList'].rvalue
        except:  # taurus3
            value = device['ExtraAttrList'].value
        attrLst = list(value)
        attrLst.sort()
        for extra in attrLst:
            self.debug("column for %s" % (extra))
            column = self._getColumn(extra)
            attrName = "%s/%s\\%s" % (watchdogName,
                                      monitoredName.replace('/', '\\'),
                                      extra)
            self.debug("attrName: %s" % (attrName))
            if Attribute(attrName).isWritable():
                self._readWriteWidget(attrName, row, column)
            else:
                self._readOnlyWidget(attrName, row, column)

    def _getColumn(self, extra):
        if extra not in self._extraColumns:
            self._extraColumns.append(extra)
            name = QtGui.QLabel("%s" % (extra), self)
            column = self._extraColumns.index(extra)+2
            self.ui.table.addWidget(name, 0, column)
            self.debug("Added the label to the header. Column %d" % column)
        else:
            column = self._extraColumns.index(extra)+2
        return column

    def _readOnlyWidget(self, model, row, column):
        widget = TaurusLabel()
        widget.setModel(model)
        self.ui.table.addWidget(widget, row, column)
        self.debug("Added a Read Only widget")

    def _readWriteWidget(self, model, row, column):
        widget = QtGui.QHBoxLayout()
        read = TaurusLabel()
        read.setModel(model)
        widget.addWidget(read, 1)
        write = TaurusValueLineEdit()
        write.setModel(model)
        widget.addWidget(write, 1)
        self.ui.table.addLayout(widget, row, column)
        self.debug("Added a Read Write widget pair")
