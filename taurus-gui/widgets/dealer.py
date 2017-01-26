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
from taurus.qt.qtgui.base import TaurusBaseComponent
from taurus.qt.qtgui.container import TaurusWidget
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


# TODO: subscribe to runningDevices to populate the self.ui.tableLayout
#       with device name, state, and the two extra attrs related with net.


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

    _model = None
    _choose = "Dealer"
    _options = "Dealers"
    _extraAttrs = ["ethernetframetransmissiondelay",
                   "ethernetinterpacketdelay"]

    def getModel(self):
        return self._model

    def setModel(self, model):
        model = str(model)
        if model != self._model:
            try:
                self.debug("New model: %s" % (model))
                choose = "%s/%s" % (model, self._choose)
                options = "%s/%s" % (model, self._options)
                self._setAttributes(choose, options)
                self._model = model
            except Exception as e:
                self.error("New model not valid: %s" % (e))
                if self._model is not None:
                    choose = "%s/%s" % (self._model, self._choose)
                    options = "%s/%s" % (self._model, self._options)
                    self._setAttributes(choose, options)
        else:
            self.warning("Set the same model than has")

    def _setAttributes(self, choose, options):
        self.ui.choose.setModel(choose)
        self.ui.options.setModel(choose)
        self._optionsListener.setModel(options)
