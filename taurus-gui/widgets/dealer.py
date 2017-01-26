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
from taurus.qt.qtgui.display import TaurusLed
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
        except:  # taurus3
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
            except:  # taurus3
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
        else:
            self.error("No widget set to introduce value names")

    def _newRow(self, devName):
        watchdogName = Attribute(self.getModel()).getParent().getNormalName()
        row = self._widget.count()
        self.info("New row %d -> %s" % (row, devName))
        name = QtGui.QLabel("%s" % (devName))
        self._widget.addWidget(name, row, 0)
        state = TaurusLed()
        state.setModel("%s/%s\\State" % (watchdogName,
                                         devName.replace('/', '\\')))
        self._widget.addWidget(state, row, 1)
        rowDct = {}
        rowDct['number'] = row
        rowDct['name'] = name
        rowDct['state'] = state
        self._rows[devName] = rowDct

    def _replaceRow(self, devName, row):
        watchdogName = Attribute(self.getModel()).getParent().getNormalName()
        self.info("Replace row %d: %s -> %s"
                  % (row['number'], str(row['name'].text()), devName))
        row['name'].setText("%s" % (devName))
        ledModel = "%s/%s\\State" % (watchdogName,
                                     devName.replace('/', '\\'))
        print ledModel
        row['state'].setModel(ledModel)

    def _removeRow(self, row):
        self.info("Remove row %d: %s"
                  % (row['number'], str(row['name'].text())))
        self._widget.removeWidget(row['name'])
        self._widget.removeWidget(row['state'])
        row['name'].deleteLater()
        row['state'].deleteLater()

    def _separateValues(self, values):
        self.info("Preparing to process %s against %s"
                  % (values, self._rows.keys()))
        new, existing, remove = [], [], []
        for value in values:
            if value in self._rows:
                existing.append(value)
                self.info("\t%s exist" % (value))
            else:
                new.append(value)
                self.info("\t%s new" % (value))
        for value in self._rows:
            if value not in values:
                remove.append(value)
                self.info("\t%s remove" % (value))
        return new, existing, remove

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
