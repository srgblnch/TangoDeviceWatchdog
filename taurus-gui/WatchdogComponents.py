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

from taurus.qt.qtgui.base import TaurusBaseComponent


class Component(TaurusBaseComponent):
    def __init__(self, parent, name=None, widget=None, devName=None):
        self._parent = parent
        self._name = None
        self._widget = None
        self._devName = None
        self._attrNames = None
        super(Component, self).__init__(name)
        self.name = name
        self.widget = widget
        self.devName = devName

    def propertyLogger(self, tag, old, new):
        if not new:
            return
        if not old:
            self.info("Setting %s: %s" % (tag, new))
        else:
            self.info("Changing %s: %s to %s" % (tag, old, new))

    @property
    def parent(self):
        return self._parent

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self.propertyLogger("Name", self._name, value)
        self._name = value

    @property
    def widget(self):
        return self._widget

    @widget.setter
    def widget(self, value):
        self.propertyLogger("Widget", self._widget, value)
        self._widget = value(parent=self._parent)
        self._doSetmodel()
        self._parent.createPanel(self._widget, name=self._name, permanent=True)

    @property
    def devName(self):
        return self._devName

    @devName.setter
    def devName(self, value):
        self.propertyLogger("DevName", self._devName, value)
        # TODO: check if it's a valid device name
        self._devName = value
        self._doSetmodel()

    @property
    def attrNames(self):
        return self._attrNames

    @attrNames.setter
    def attrNames(self, value):
        self.propertyLogger("AttrNames", self._attrNames, value)
        # TODO: check if it's a list of strings (possible attribute names)
        self._attrNames = value
        self._doSetmodel()

    def _doSetmodel(self):
        try:
            if hasattr(self._widget, 'setModel'):
                if self._devName:
                    if self._setModelWithAttrs(self._devName):
                        return True
                    else:
                        self._setDeviceAsModel(self._devName)
                else:
                    self.error("No conditions for setModel()")
        except Exception as e:
            self.error("Cannot do setModel: %s" % (e))
        return False

    def _setDeviceAsModel(self, devName):
        self._widget.setModel(devName)

    def _setModelWithAttrs(self, devName):
        if self._attrNames:
            model = []
            for attrName in self._attrNames:
                model.append("%s/%s" % (devName, attrName))
            self._widget.setModel(model)
            self.info("setmodel(%s)" % (self._widget.getModel()))
            return True
        return False
