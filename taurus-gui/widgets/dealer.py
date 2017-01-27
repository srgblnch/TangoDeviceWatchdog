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
from taurus import Attribute
from taurus.core.taurusbasetypes import TaurusEventType
from taurus.external.qt import QtGui
from taurus.qt.qtgui.base import TaurusBaseComponent
from taurus.qt.qtgui.container import TaurusWidget
from taurus.qt.qtgui.display import TaurusLed, TaurusLabel
from taurus.qt.qtgui.input import TaurusValueLineEdit
from taurus.qt.qtgui.util.ui import UILoadable


class OptionsListener(TaurusBaseComponent):
    '''
        Subscribe to the Dealers attribute, in case it changes (device
        restart adding or removing one or many) the gui must refresh.
    '''
    def __init__(self, parent=None, name=None, designMode=False):
        # super(OptionsListener, self).__init__()
        self.call__init__(TaurusBaseComponent, name, parent)

    _widget = None

    def getWidget(self):
        return self._widget

    def setWidget(self, widget):
        self._widget = widget

    def setModel(self, model):
        # FIXME: this is unnecessary in taurus4
        TaurusBaseComponent.setModel(self, model)
        try:  # taurus4
            values = Attribute(model).rvalue
        except AttributeError as e:  # taurus3
            values = Attribute(model).read().value
        self._setValueNames(values)

    def handleEvent(self, evt_src, evt_type, evt_value):
        model = self.getModel()
        if str(evt_src) != Attribute(model).getFullName():
            self.warning("Event received from %s that doesn't "
                         "correspond to the model %s" % (evt_src, model))
            return
        if evt_type in (TaurusEventType.Change,
                        TaurusEventType.Periodic)\
                and evt_value is not None:
            self._setValueNames(evt_value.rvalue)
        elif evt_type == TaurusEventType.Config:
            self._setValueNames(evt_value.rvalue)
        else:
            self.warning("Unhandled type of event %s with value %s"
                         % (evt_type, evt_value))

    def _setValueNames(self, values):
        if self._widget is not None:
            if hasattr(self._widget, 'setValueNames'):
                # self.debug("setValueNames to the combobox: %s"
                #            % (str(values)))
                # currentItems = [self._widget.itemText(i)
                #                 for i in range(self._widget.count())]
                self._widget.setValueNames([[e, e] for e in values])
            else:
                self.warning("Impossible to set value names in a widget type"
                             " %s" % (type(self._widget)))
        else:
            self.error("No widget set to introduce value names")


class RunningLayout(TaurusBaseComponent):
    '''
        subscribe to runningDevices to populate the self.ui.tableLayout
        with device name, state, and the two extra attrs related with net.
    '''
    def __init__(self, parent=None, name=None, designMode=False):
        # super(OptionsListener, self).__init__()
        self.call__init__(TaurusBaseComponent, name, parent)

    _widget = None
    _header = {}
    _rows = {}
    _extraAttrs = ["ethernetframetransmissiondelay",
                   "ethernetinterpacketdelay"]

    def getWidget(self):
        return self._widget

    def setWidget(self, widget):
        self._widget = widget

    def setModel(self, model):
        currentModel = self.getModel()
        if model != currentModel:
            if currentModel is None:
                self._cleanLayout()
            # FIXME: this is unnecessary in taurus4
            TaurusBaseComponent.setModel(self, model)
            try:  # taurus4
                values = Attribute(model).rvalue
            except AttributeError as e:  # taurus3
                values = Attribute(model).read().value
            self._buildLayout(values)

    def handleEvent(self, evt_src, evt_type, evt_value):
        model = self.getModel()
        if str(evt_src) != Attribute(model).getFullName():
            self.warning("Event received from %s that doesn't "
                         "correspond to the model %s" % (evt_src, model))
            return
        if evt_type in (TaurusEventType.Change,
                        TaurusEventType.Periodic)\
                and evt_value is not None:
            self._buildLayout(evt_value.rvalue)
        elif evt_type == TaurusEventType.Config:
            self._buildLayout(evt_value.rvalue)
        else:
            self.warning("Unhandled type of event %s with value %s"
                         % (evt_type, evt_value))

    def _buildLayout(self, values):
        values = list(values)
        if self._widget is not None:
            new, existing, remove = self._separateValues(values)
            for value in new:
                if len(remove) != 0:
                    self._replaceRow(value, self._rows[remove[0]])
                    remove.pop(0)
                else:
                    self._newRow(value)
            for value in remove:
                self._removeRow(self._rows[value])
                self._rows.pop(value)
            if len(self._rows.keys()) == 0:
                self._removeHeader()
            self.debug("Layout updated to %s" % (self._rows.keys()))
        else:
            self.error("No widget set to introduce value names")

    def _newRow(self, devName):
        watchdogName = Attribute(self.getModel()).getParent().getNormalName()
        row = self._widget.count()
        if row == 0:
            self._addHeader()
            row += 1
        self.debug("New row %d -> %s" % (row, devName))
        name = self._buildLabel(devName, row)
        state = self._buildLed(devName, row)
        rowDct = {}
        rowDct['number'] = row
        rowDct['name'] = name
        rowDct['state'] = state
        for i, attrName in enumerate(self._extraAttrs):
            rowDct[attrName] = self._buildExtraAttr(devName, attrName,
                                                    row, i+2)
        self._rows[devName] = rowDct

    def _replaceRow(self, devName, row):
        watchdogName = Attribute(self.getModel()).getParent().getNormalName()
        self.debug("Replace row %d: %s -> %s"
                   % (row['number'], str(row['name'].text()), devName))
        row['name'].setText("%s" % (devName))
        row['state'].setModel(self._buildLedName(devName))
        for attrName in self._extraAttrs:
            model = self._getWatchdogAttrName(devName, attrName)
            row[attrName]['read'].setModel(model)
            row[attrName]['write'].setModel(model)

    def _removeRow(self, row):
        self.debug("Remove row %d: %s"
                   % (row['number'], str(row['name'].text())))
        self._widget.removeWidget(row['name'])
        self._widget.removeWidget(row['state'])
        row['name'].deleteLater()
        row['state'].deleteLater()
        for attrName in self._extraAttrs:
            self._widget.removeItem(row[attrName]['layout'])
            row[attrName]['read'].deleteLater()
            row[attrName]['write'].deleteLater()
            row[attrName]['layout'].deleteLater()

    def _addHeader(self):
        for i, attrName in enumerate(self._extraAttrs):
            label = Attribute("%s/%s" % (self._getWatchdog(), attrName)).label
            self._header[attrName] = QtGui.QLabel("%s" % (label))
            self._widget.addWidget(self._header[attrName], 0, i+2)

    def _removeHeader(self):
        for attrName in self._extraAttrs:
            if attrName in self._header:
                label = self._header.pop(attrName)
                self._widget.removeWidget(label)
                label.deleteLater()
            else:
                self.error("Cannot remove header %s from %s"
                           % (attrName, self._header.keys()))

    def _separateValues(self, values):
        self.debug("Preparing to process %s against %s"
                   % (values, self._rows.keys()))
        new, existing, remove = [], [], []
        for value in values:
            if value in self._rows:
                existing.append(value)
                self.debug("\t%s exist" % (value))
            else:
                new.append(value)
                self.debug("\t%s new" % (value))
        for value in self._rows:
            if value not in values:
                remove.append(value)
                self.debug("\t%s remove" % (value))
        return new, existing, remove

    def _getWatchdog(self):
        return Attribute(self.getModel()).getParent().getNormalName()

    def _getWatchdogAttrName(self, devName, attrName):
        watchdogName = self._getWatchdog()
        return "%s/%s\\%s" % (watchdogName, devName.replace('/', '\\'),
                              attrName)

    def _buildLabel(self, model, r):
        name = QtGui.QLabel("%s" % (model))
        self._widget.addWidget(name, r, 0)
        return name

    def _buildLedName(self, name):
        watchdogName = self._getWatchdog()
        ledName = self._getWatchdogAttrName(name, 'State')
        self.debug("Led %s -> %s" % (name, ledName))
        return ledName

    def _buildLed(self, model, r):
        led = TaurusLed()
        led.setModel("%s" % (self._buildLedName(model)))
        self._widget.addWidget(led, r, 1)
        return led

    def _buildExtraAttr(self, devName, attrName, r, c):
        model = self._getWatchdogAttrName(devName, attrName)
        widget = QtGui.QHBoxLayout()
        read = TaurusLabel()
        read.setModel(model)
        widget.addWidget(read, 1)
        write = TaurusValueLineEdit()
        write.setModel(model)
        widget.addWidget(write, 1)
        self._widget.addLayout(widget, r, c)
        return {'layout': widget, 'read': read, 'write': write}

    def _buildTaurusLabel(self, model, r, c):
        label = TaurusLabel()
        label.setModel("%s" % (model))
        return label

    def _buildLineEdit(self, model, r, c):
        edit = TaurusValueLineEdit()
        edit.setModel("%s" % (model))
        return edit

    def _cleanLayout(self):
        pass


ui_filename = "dealer.ui"


@UILoadable(with_ui="ui")
class Dealer(TaurusWidget):
    def __init__(self, parent=None, name=None, designMode=False):
        super(Dealer, self).__init__()
        basePath = os.path.dirname(__file__)
        if len(basePath) == 0:
            basePath = '.'
        self.loadUi(filename=ui_filename, path=basePath+"/ui")
        self.ui.options.setAutoApply(True)
        self._optionsListener = OptionsListener(self)
        self._optionsListener.setWidget(self.ui.options)
        self._runningLayout = RunningLayout(self)
        self._runningLayout.setWidget(self.ui.devList)

    _model = None
    _choose = "Dealer"
    _options = "Dealers"
    _running = "RunningDevicesList"

    def getModel(self):
        return self._model

    def setModel(self, model):
        model = str(model)
        if model != self._model:
            try:
                self.debug("New model: %s" % (model))
                choose = "%s/%s" % (model, self._choose)
                options = "%s/%s" % (model, self._options)
                running = "%s/%s" % (model, self._running)
                self._setAttributes(choose, options, running)
                self._model = model
            except Exception as e:
                self.error("New model not valid: %s" % (e))
                if self._model is not None:
                    choose = "%s/%s" % (self._model, self._choose)
                    options = "%s/%s" % (self._model, self._options)
                    running = "%s/%s" % (self._model, self._running)
                    self._setAttributes(choose, options, running)
        else:
            self.warning("Set the same model than has")

    def _setAttributes(self, choose, options, running):
        self.ui.choose.setModel(choose)
        self.ui.options.setModel(choose)
        self._optionsListener.setModel(options)
        self._runningLayout.setModel(running)
