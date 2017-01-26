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

import sys
try:
    from taurus import Authority, Logger
except:  # taurus 3
    from taurus import Database as Authority
    from taurus import Logger
from taurus.qt.qtgui.util.ui import UILoadable
from taurus.qt.qtgui.container import TaurusWidget
from taurus.external.qt import Qt, QtGui, QtCore

####
# Extra furniture for PyQt4.4 & numpy 1.3 backward compatibility ---
try:  # normal way
    from taurus.external.qt import Qt, QtGui, QtCore
except:  # backward compatibility to pyqt 4.4.3
    from taurus.qt import Qt, QtGui


class MyQtSignal(Logger):
    '''This class is made to emulate the pyqtSignals for too old pyqt versions.
    '''
    def __init__(self, name, parent=None):
        Logger.__init__(self)
        self._parent = parent
        self._name = name
        self._cb = []

    def emit(self):
        self.info("Signal %r emit (%s)" % (self._name, self._cb))
        Qt.QObject.emit(self._parent, Qt.SIGNAL(self._name))
        self.debug("Having callback list of %d elements" % (len(self._cb)))
        for cb in self._cb:
            self.debug("Calling %r" % (cb))
            cb()

    def connect(self, callback):
        self.error("Trying a connect on MyQtSignal(%s)" % (self._name))
        # raise Exception("Invalid")
        self._cb.append(callback)


@UILoadable(with_ui='_ui')
class TaurusDevCombo(TaurusWidget):
    try:
        modelChosen = QtCore.pyqtSignal()
    except:
        modelChosen = MyQtSignal('modelChosen')

    def __init__(self, parent=None, designMode=False):
        TaurusWidget.__init__(self, parent, designMode=designMode)
        self.loadUi(filename="taurusDevCombo.ui")
        self._selectedDevice = ""
        if hasattr(self.modelChosen, '_parent'):
            self.modelChosen._parent = self
        try:
            self._ui.selectorCombo.currentIndexChanged.connect(self.selection)
        except Exception as e:
            self.warning("Using deprecated connect signal")
            Qt.QObject.connect(self._ui.selectorCombo,
                               Qt.SIGNAL('currentIndexChanged(int)'),
                               self.selection)

    @classmethod
    def getQtDesignerPluginInfo(cls):
        ret = TaurusWidget.getQtDesignerPluginInfo()
        ret['module'] = 'widgets.TaurusDevCombo'
        ret['group'] = 'Taurus Views'
        ret['container'] = ':/designer/frame.png'
        ret['container'] = False
        return ret

    def setModel(self, model):
        self.getDeviceListByDeviceServerName(model)
        self._ui.selectorCombo.addItems(self._deviceNames.keys())

    def getDeviceListByDeviceServerName(self, deviceServerName):
        authority = Authority()
        foundInstances = authority.getServerNameInstances(deviceServerName)
        self.debug("by %s found %d instances: %s."
                   % (deviceServerName, len(foundInstances),
                      ','.join("%s" % (instance.name())
                               for instance in foundInstances)))
        self._deviceNames = {}
        for instance in foundInstances:
            for i, devName in enumerate(instance.getDeviceNames()):
                if not devName.startswith('dserver'):
                    self._deviceNames[devName] = instance.getClassNames()[i]
        return self._deviceNames.keys()

    def selection(self, devName):
        if type(devName) == int:
            devName = self._ui.selectorCombo.currentText()
        if devName not in self._deviceNames.keys():
            self.warning("Selected device is not "
                         "in the list of devices found!")
        self.debug("selected %s" % (devName))
        self._selectedDevice = devName
        self.modelChosen.emit()

    def getSelectedDeviceName(self):
        # self.debug("Requested which device was selected")
        return self._selectedDevice

    def getSelectedDeviceClass(self):
        try:
            return self._deviceNames[self._selectedDevice]
        except:
            self.error("Uou! As the selected device is not in the device "
                       "instances found, its class is unknown")
            return "unknown"


def main():
    app = Qt.QApplication(sys.argv)
    w = TaurusDevCombo()
    w.setModel("MeasuredFillingPattern")
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
