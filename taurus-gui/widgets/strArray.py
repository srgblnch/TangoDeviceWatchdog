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

from taurus.core.taurusbasetypes import TaurusEventType
from taurus.external.qt import Qt
from taurus.qt.qtgui.container import TaurusWidget


class StringArrayWidget(TaurusWidget):
    def __init__(self, parent=None, designMode=False,
                 defaultWriteMode=None):
        TaurusWidget.__init__(self, parent=parent, designMode=designMode)
        self._text = Qt.QTextEdit(self)
        self._text.setReadOnly(True)

    @classmethod
    def getQtDesignerPluginInfo(cls):
        ret = TaurusWidget.getQtDesignerPluginInfo()
        ret['module'] = 'widgets.strArray'
        ret['group'] = 'Taurus Views'
        ret['icon'] = "designer:table.png"
        return ret

    def handleEvent(self, evt_src, evt_type, evt_value):
        model = self.getModel()
        if model == evt_src:
            self.warning("Event received from %s that doesn't "
                         "correspond with %s" % (model, evt_src))
            return
        if evt_type in (TaurusEventType.Change,
                        TaurusEventType.Periodic)\
                and evt_value is not None:
            self._text.setText(self._list2lines(evt_value.value))
        elif evt_type == TaurusEventType.Config:
            attr = self.getModelObj()
            value = attr.read().value
            self._text.setText(self._list2lines(value))

    def _list2lines(self, lst):
        if type(lst) in [list, tuple] and len(lst) > 0:
            return "".join("%s\n" % e for e in lst)
        return ''
