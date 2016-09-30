#!/usr/bin/env python
# -*- coding:utf-8 -*-

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
__copyright__ = "Copyright 2016 CELLS/Alba synchrotron"
__license__ = "GPLv3+"
__status__ = "development"

__all__ = ["Watchdog", "WatchdogClass", "main"]
__docformat__ = 'restructuredtext'


from Dog import Dog
import email.mime.text
import PyTango
import smtplib
from socket import gethostname
import sys
from threading import Event
from time import time
import traceback
from types import StringType


# # Device States Description:
# INIT : during the events subscription and prepare.
# ON : when is normally running.
# ALARM : at least one sector can be too busy for the number of active cameras.
# FAULT : When something when wrong.


class Watchdog(PyTango.Device_4Impl):
    ##################
    # ---# Logs region
    def cleanAllImportantLogs(self):
        # @todo: clean the important logs when they loose importance.
        self.debug_stream("In %s::cleanAllImportantLogs()" % (self.get_name()))
        self._important_logs = []
        self.addStatusMsg("")

    def addStatusMsg(self, current, important=False):
        self.debug_stream("In %s::addStatusMsg()" % (self.get_name()))
        msg = "The device is in %s state.\n" % (self.get_state())
        for ilog in self._important_logs:
            msg = "%s%s\n" % (msg, ilog)
        status = "%s%s\n" % (msg, current)
        self.set_status(status)
        self.push_change_event('Status', status)
        if important and current not in self._important_logs:
            self._important_logs.append(current)

    def change_state(self, newstate):
        self.debug_stream("In %s::change_state(%s)"
                          % (self.get_name(), str(newstate)))
        self.set_state(newstate)
        self.push_change_event('State', newstate)
        self.cleanAllImportantLogs()
    # --- Done Logs region
    ######################

    #########################
    # ---# Process Properties
    def _processDevicesListProperty(self):
        '''This method works with the raw input in the property DevicesList
           to convert it in the expected dictionary and do all the state
           event subscriptions.
        '''
        self.info_stream("In %s::_processDevicesListProperty() DevicesList = "
                         "%r" % (self.get_name(), self.DevicesList))
        for i in range(len(self.DevicesList)):
            subline = self.DevicesList[i].split(',')
            for j in range(len(subline)):
                if len(subline[j]) > 0:
                    try:
                        devName = subline[j].lower()
                        dog = Dog(devName, self._joinerEvent, self)
                        dog.tryFaultRecovery = self.TryFaultRecover
                        dog.tryHangRecovery = self.TryHangRecover
                        self.DevicesDict[devName] = dog
                    except Exception as e:
                        errMsg = "In %s::_processDevicesListProperty() "\
                                 "Exception in DevicesList processing: "\
                                 "%d line, %d element, exception: %s"\
                                 % (self.get_name(), i, j, str(e))
                        self.error_stream(errMsg)
                        traceback.print_exc()
        # per each of those cameras
        for devName in self.DevicesDict.keys():
            dynAttrName = "%s_State" % (devName.replace("/", "_"))
            # Replace by an "impossible" symbol
            # --- FIXME: the separator would be improved
            dynAttr = PyTango.Attr(dynAttrName, PyTango.DevUShort,
                                   PyTango.READ)
            # --- FIXME: Can the dynAttr be a DevState type?
            self.add_attribute(dynAttr, r_meth=Watchdog.read_oneDeviceState,
                               is_allo_meth=Watchdog.is_oneDeviceState_allowed)
            self.debug_stream("In %s::processDevicesList() add dyn_attr %s"
                              % (self.get_name(), dynAttrName))
    # --- Done Process Properties
    #############################

    ######################
    # ---# dyn_attr region
    def read_oneDeviceState(self, attr):
        self.debug_stream("In %s::read_oneDeviceState()" % (self.get_name()))
        devName = attr.get_name().replace("--", "/")
        try:
            state = self.DevicesDict[devName].devState
            if state:
                attr.set_value(state)
            else:
                attr.set_value_date_quality(PyTango.DevState.UNKNOWN, time(),
                                            PyTango.AttrQuality.ATTR_INVALID)
        except:
            attr.set_value(PyTango.DevState.UNKNOWN)

    def is_oneDeviceState_allowed(self, req_type):
        if self.get_state() in [PyTango.DevState.FAULT]:
            #    End of Generated Code
            #    Re-Start of Generated Code
            return False
        return True

    # TODO: more dynamic attributes:
    #       - allow to adjust the {Fault,Hand}Recovery for each of the watched
    #         (remember to make them memorised).
    #       - allow to adjust the recheck period for each of the watched
    #       - report threshold for running devices

    # --- Done dyn_attr region
    ##########################

    ####################
    # ---# events region
    def fireEventsList(self, eventsAttrList):
        timestamp = time()
        attrNames = []
        for attrEvent in eventsAttrList:
            try:
                attrName = attrEvent[0]
                attrValue = attrEvent[1]
                attrNames.append(attrName)
                self.debug_stream("In %s::fireEventsList() attribute: %s, "
                                  "value: %s" % (self.get_name(), attrName,
                                                 str(attrValue)))
                # FIXME: is this CyclicBuffer something useless?
                #        (from a copypaste maybe?)
                if attrName in ['CyclicBuffer'] and\
                        not self.attr_emitCyclicBuffer_read:
                    self.debug_stream("In %s::fireEventsList() attribute: %s "
                                      "avoided to emit the event due to flag."
                                      % (self.get_name(), attrName))
                    attrQuality = None
                elif len(attrEvent) == 3:  # specifies quality
                    attrQuality = attrEvent[2]
                else:
                    attrQuality = PyTango.AttrQuality.ATTR_VALID
                if attrQuality:
                    self.push_change_event(attrName, attrValue,
                                           timestamp, attrQuality)
            except Exception as e:
                self.error_stream("In %s::fireEventsList() Exception "
                                  "with attribute %s:\n%s"
                                  % (self.get_name(), attrEvent[0], e))
        if len(attrNames) > 0:
            self.info_stream("In %s::fireEventsList() emitted %d events: %s"
                             % (self.get_name(), len(attrNames), attrNames))
    # --- Done events region
    ########################

    ################
    # --- Dog region
    def isInRunningLst(self, who):
        return self.isInLst(self.attr_RunningDevicesList_read, who)

    def appendToRunning(self, who):
        if self.appendToLst(self.attr_RunningDevicesList_read, "Running", who):
            self.fireRunningAttrEvents()

    def removeFromRunning(self, who):
        if self.removeFromLst(self.attr_RunningDevicesList_read, "Running",
                              who):
            self.fireRunningAttrEvents()

    def fireRunningAttrEvents(self):
        self.attr_RunningDevices_read = len(self.attr_RunningDevicesList_read)
        self.fireEventsList([["RunningDevices", self.attr_RunningDevices_read],
                             ["RunningDevicesList",
                              self.attr_RunningDevicesList_read]])

    def isInFaultLst(self, who):
        return self.isInLst(self.attr_FaultDevicesList_read, who)

    def appendToFault(self, who):
        if self.appendToLst(self.attr_FaultDevicesList_read, "Fault", who):
            self.fireFaultAttrEvents()

    def removeFromFault(self, who):
        if self.removeFromLst(self.attr_FaultDevicesList_read, "Fault", who):
            self.fireFaultAttrEvents()

    def fireFaultAttrEvents(self):
        self.attr_FaultDevices_read = len(self.attr_FaultDevicesList_read)
        self.fireEventsList([["FaultDevices", self.attr_FaultDevices_read],
                             ["FaultDevicesList",
                              self.attr_FaultDevicesList_read]])

    def isInHangLst(self, who):
        return self.isInLst(self.attr_HangDevicesList_read, who)

    def appendToHang(self, who):
        if self.appendToLst(self.attr_HangDevicesList_read, "Hang", who):
            self.fireHangAttrEvents()

    def removeFromHang(self, who):
        if self.removeFromLst(self.attr_HangDevicesList_read, "Hang", who):
            self.fireHangAttrEvents()

    def fireHangAttrEvents(self):
        self.attr_HangDevices_read = len(self.attr_HangDevicesList_read)
        self.fireEventsList([["HangDevices", self.attr_HangDevices_read],
                             ["HangDevicesList",
                              self.attr_HangDevicesList_read]])

    def isInLst(self, lst, who):
        return lst.count(who)

    def appendToLst(self, lst, name, who):
        if not lst.count(who):
            lst.append(who)
            self.info_stream("%s append to %s list" % (who, name))
            return True
        else:
            self.warn_stream("%s was already in the %s list" % (who, name))
            return False

    def removeFromLst(self, lst, name, who):
        if lst.count(who):
            lst.pop(lst.index(who))
            self.info_stream("%s removed from %s list" % (who, name))
            return True
        else:
            self.warn_stream("%s was NOT in the %s list" % (who, name))
            return False

    def mailto(self, action, msg):
        if len(self.MailTo) != 0:
            name = self.get_name()  # .replace('/', '_')
            mail = email.mime.text.MIMEText(msg)
            mail['From'] = "%s@%s" % (name, gethostname())
            mail['To'] = ', '.join(self.MailTo)
            mail['Subject'] = "[%s] %s" % (self.get_name(), action)
            s = smtplib.SMTP('localhost')
            s.sendmail(mail['From'], self.MailTo, mail.as_string())
            s.quit()
    # --- Done dog region
    #####################

    def __init__(self, cl, name):
        PyTango.Device_4Impl.__init__(self, cl, name)
        self.debug_stream("In __init__()")
        Watchdog.init_device(self)

    def delete_device(self):
        self.debug_stream("In delete_device()")
        self._joinerEvent.set()
        # TODO: check the stop process for each of the dogs

    def init_device(self):
        self.debug_stream("In init_device()")
        self.get_device_properties(self.get_device_class())
        # --- set the vbles
        self.DevicesDict = {}
        self.attr_RunningDevices_read = 0
        self.attr_RunningDevicesList_read = []
        self.attr_FaultDevices_read = 0
        self.attr_FaultDevicesList_read = []
        self.attr_HangDevices_read = 0
        self.attr_HangDevicesList_read = []
        # --- prepare attributes that will have events ----
        self.set_change_event('State', True, False)
        self.set_change_event('Status', True, False)
        self.change_state(PyTango.DevState.INIT)
        self.set_change_event('RunningDevices', True, False)
        self.set_change_event('RunningDevicesList', True, False)
        self.set_change_event('FaultDevices', True, False)
        self.set_change_event('FaultDevicesList', True, False)
        self.set_change_event('HangDevices', True, False)
        self.set_change_event('HangDevicesList', True, False)
        # --- tools for the Exec() cmd
        DS_MODULE = __import__(self.__class__.__module__)
        kM = dir(DS_MODULE)
        vM = map(DS_MODULE.__getattribute__, kM)
        self.__globals = dict(zip(kM, vM))
        self.__globals['self'] = self
        self.__globals['module'] = DS_MODULE
        self.__locals = {}
        # --- process properties
        self._joinerEvent = Event()
        self._joinerEvent.clear()
        self._processDevicesListProperty()
        # everything ok:
        self.change_state(PyTango.DevState.ON)

    def always_executed_hook(self):
        self.debug_stream("In always_excuted_hook()")

    # -------------------------------------------------------------------------
    #    Watchdog read/write attribute methods
    # -------------------------------------------------------------------------
    def read_RunningDevices(self, attr):
        self.debug_stream("In read_RunningDevices()")
        attr.set_value(self.attr_RunningDevices_read)

    def read_FaultDevices(self, attr):
        self.debug_stream("In read_FaultDevices()")
        attr.set_value(self.attr_FaultDevices_read)

    def read_HangDevices(self, attr):
        self.debug_stream("In read_HangDevices()")
        attr.set_value(self.attr_HangDevices_read)

    def read_RunningDevicesList(self, attr):
        self.debug_stream("In read_RunningDevicesList()")
        attr.set_value(self.attr_RunningDevicesList_read)

    def read_FaultDevicesList(self, attr):
        self.debug_stream("In read_FaultDevicesList()")
        attr.set_value(self.attr_FaultDevicesList_read)

    def read_HangDevicesList(self, attr):
        self.debug_stream("In read_HangDevicesList()")
        attr.set_value(self.attr_HangDevicesList_read)

    def initialize_dynamic_attributes(self):
        pass

    def read_attr_hardware(self, data):
        self.debug_stream("In read_attr_hardware()")


# =============================================================================
#    Watchdog command methods
# =============================================================================

# -----------------------------------------------------------------------------
#    Exec command:
# -----------------------------------------------------------------------------
    def Exec(self, argin):
        """ Hackish expert attribute to look inside the device during
        execution. If you use it, be very careful and at your own risk.
        :param argin:
        :type: PyTango.DevString
        :return: argout:
        :rtype: PyTango.DevString """
        self.debug_stream("In "+self.get_name()+".Exec()")
        argout = ''
        try:
            try:
                # interpretation as expression
                argout = eval(argin, self.__globals, self.__locals)
            except SyntaxError:
                # interpretation as statement
                exec argin in self.__globals, self.__locals
                argout = self.__locals.get("y")

        except Exception, exc:
            # handles errors on both eval and exec level
            argout = traceback.format_exc()

        if type(argout) == StringType:
            return argout
        elif isinstance(argout, BaseException):
            return "%s!\n%s" % (argout.__class__.__name__, str(argout))
        else:
            try:
                return pprint.pformat(argout)
            except Exception:
                return str(argout)
        return argout


class WatchdogClass(PyTango.DeviceClass):
    def dyn_attr(self, dev_list):
        """Invoked to create dynamic attributes for the given devices.
        Default implementation calls
        :meth:`Watchdog.initialize_dynamic_attributes` for each device
        :param dev_list: list of devices
        :type dev_list: :class:`PyTango.DeviceImpl`"""
        for dev in dev_list:
            try:
                dev.initialize_dynamic_attributes()
            except:
                import traceback
                dev.warn_stream("Failed to initialize dynamic attributes")
                dev.debug_stream("Details: " + traceback.format_exc())

    #    Class Properties
    class_property_list = {
        }

    #    Device Properties
    device_property_list = {
        'DevicesList':
            [PyTango.DevVarStringArray,
             "Dictionary convertible string with an internal label as a key "
             "and its device name as item.",
             []],
        'SectorsList':
            [PyTango.DevVarStringArray,
             "Dictionary convertible string with sectors as key and the item "
             "is a list of tags from the DeviceList.",
             []],
        'TryFaultRecover':
            [PyTango.DevBoolean,
             "Flag to tell the device that, if possible, try to recover "
             "cameras in fault state",
             []],
        'TryHangRecover':
            [PyTango.DevBoolean,
             "Flag to tell the device that, if possible, try to recover hang "
             "cameras",
             []],
        'MailTo':
            [PyTango.DevVarStringArray,
             "List of mail destinations to report when fault or hang lists "
             "changes",
             []]
        }

    #    Command definitions
    cmd_list = {
        'Exec':
            [[PyTango.DevString, "none"],
             [PyTango.DevString, "none"],
             {'Display level': PyTango.DispLevel.EXPERT}],
        }

    #    Attribute definitions
    attr_list = {
        'RunningDevices':
            [[PyTango.DevUShort,
              PyTango.SCALAR,
              PyTango.READ],
             {'description': "Number of ccd running state in total."}],
        'FaultDevices':
            [[PyTango.DevUShort,
              PyTango.SCALAR,
              PyTango.READ],
             {'description': "Number of ccd in fault state in total."}],
        'HangDevices':
            [[PyTango.DevUShort,
              PyTango.SCALAR,
              PyTango.READ],
             {'description': "Number of ccd non accessible in total."}],
        'RunningDevicesList':
            [[PyTango.DevString,
              PyTango.SPECTRUM,
              PyTango.READ, 999]],
        'FaultDevicesList':
            [[PyTango.DevString,
              PyTango.SPECTRUM,
              PyTango.READ, 999]],
        'HangDevicesList':
            [[PyTango.DevString,
              PyTango.SPECTRUM,
              PyTango.READ, 999]],
        }


def main():
    try:
        py = PyTango.Util(sys.argv)
        py.add_class(WatchdogClass, Watchdog, 'Watchdog')

        U = PyTango.Util.instance()
        U.server_init()
        U.server_run()

    except PyTango.DevFailed as e:
        print '-------> Received a DevFailed exception:', e
    except Exception as e:
        print '-------> An unforeseen exception occured....', e

if __name__ == '__main__':
    main()
