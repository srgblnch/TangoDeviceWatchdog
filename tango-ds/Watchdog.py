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


from dealer import BuildDealer
from dog import Dog, DEFAULT_RECHECK_TIME, SEPARATOR
import email.mime.text
import PyTango
import smtplib
from socket import gethostname
import sys
from threading import Thread, Event, Lock
from time import ctime, sleep, time
import traceback
from types import StringType


COLLECTION_REPORT_PERIOD = 3600*8  # every 8h, three times a day


# # Device States Description:
# INIT : during the events subscription and prepare.
# ON : when is normally running.
# ALARM : at least one sector can be too busy for the number of active cameras.
# FAULT : When something when wrong.


class Watchdog(PyTango.Device_4Impl):
    ##################
    # # Logs region ---
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
    # Done Logs region ---
    ######################

    #########################
    # # Process Properties ---
    def _processDevicesListProperty(self):
        '''This method works with the raw input in the property DevicesList
           to convert it in the expected dictionary and do all the state
           event subscriptions.
        '''
        # FIXME: too large method
        self._allDevices = []
        for i in range(len(self.DevicesList)):
            subline = self.DevicesList[i].split(',')
            for j in range(len(subline)):
                if len(subline[j]) > 0:
                    try:
                        devName = subline[j].lower()
                        self._allDevices.append(devName)
                    except Exception as e:
                        errMsg = "In %s::_processDevicesListProperty() "\
                                 "Exception in DevicesList processing: "\
                                 "%d line, %d element, exception: %s"\
                                 % (self.get_name(), i, j, str(e))
                        self.error_stream(errMsg)
                        traceback.print_exc()
        timeSeparation = DEFAULT_RECHECK_TIME/len(self._allDevices)
        self.info_stream("In %s::_processDevicesListProperty() %d in elements "
                         "(%g seconds time separation) DevicesList = %r"
                         % (self.get_name(), len(self._allDevices),
                            timeSeparation, self._allDevices))
        alldevNames = PyTango.SpectrumAttr('DevicesList', PyTango.DevString,
                                           PyTango.READ, 1000)
        self.add_attribute(alldevNames, self._readAllDevNames)
        self._extraAttrs = self._prepare_ExtraAttrs()
        allExtraAttrs = PyTango.SpectrumAttr('ExtraAttrList',
                                             PyTango.DevString,
                                             PyTango.READ, 1000)
        self.add_attribute(allExtraAttrs, self._readAllExtraAttrs)
        extraAttrsDct = {}
        for attrName in self._extraAttrs:
            extraAttrsDct[attrName] = []
        for i, devName in enumerate(self._allDevices):
            try:
                self._build_WatchedStateAttribute(devName)
                for attrName in self._extraAttrs:
                    extraAttrsDct[attrName].append(self._build_ExtraAttr
                                                   (devName, attrName))
                startDelay = timeSeparation*i
                self.info_stream("for %d. device %s there will be a delay "
                                 "of %g seconds" % (i+1, devName,
                                                    startDelay))
                dog = Dog(devName, self._joinerEvent, startDelay,
                          self._extraAttrs, self)
                dog.tryFaultRecovery = self.TryFaultRecover
                dog.tryHangRecovery = self.TryHangRecover
                self.DevicesDict[devName] = dog
            except Exception as e:
                errMsg = "In %s::_processDevicesListProperty() "\
                         "Exception in Dogs generation: "\
                         "%d:%s, exception: %s"\
                         % (self.get_name(), i, devName, str(e))
                self.error_stream(errMsg)
                traceback.print_exc()
        for attrName in self._extraAttrs:
            attrTypes = extraAttrsDct[attrName]
            if len(attrTypes) != len(self._allDevices):
                self.error_stream("Not all the device succeed building the "
                                  "extraAttr %s" % (attrName))
            elif all(attrTypes) != attrTypes[0]:
                self.error_stream("Not all the devices have the same attrType "
                                  "for %s" % (attrName))
            extraAttrLst = PyTango.SpectrumAttr(attrName, attrTypes[0],
                                                PyTango.READ, 1000)
            self.add_attribute(extraAttrLst, self._readExtraAttrLst)
        self._buildDealer()

    def _buildDealer(self):
        try:
            self._buildDealerAttrs()
            self._rebuildDealer()
        except Exception as e:
            self.error_stream("Exception building the dealer: %s" % (e))
            traceback.print_exc()
        else:
            self.info_stream("Dealer build")

    def _buildDealerAttrs(self):
        # list of possible dealers
        dealerOptions = PyTango.SpectrumAttr('Dealers', PyTango.DevString,
                                             PyTango.READ, 10)
        self.add_attribute(dealerOptions, self.read_Dealers)
        # dealer in use (required to be memorised)
        dealerAttr = PyTango.Attr('Dealer', PyTango.DevString,
                                  PyTango.READ_WRITE)
        dealerAttr.set_memorized()
        dealerAttr.set_memorized_init(True)
        self.add_attribute(dealerAttr, self.read_Dealer, self.write_Dealer)
        # TODO: dealer configurations (min, max, ...)

    def _rebuildDealer(self, value='Equidistant'):
        dealerLst = []  # Hackish!!!
        for bar in self.DealerAttrList:
            subLst = bar.split(',')
            for foo in subLst:
                dealerLst.append(foo.strip())
        dogsLst = self.DevicesDict.values()
        statesLst = [PyTango.DevState.RUNNING]
        if value == 'Equidistant':
            distance = 1000
        elif value == 'MinMax':
            distance = [0, 5000]
        else:
            return
        self._dealer = BuildDealer(value, attrLst=dealerLst,
                                   dogsLst=dogsLst, statesLst=statesLst,
                                   distance=distance, parent=self)

    def _build_WatchedStateAttribute(self, devName):
        dynAttrName = "%s%sState"\
            % (devName.replace("/", SEPARATOR), SEPARATOR)
        # Replace by an "impossible" symbol
        # --- FIXME: the separator would be improved
        aprop = PyTango.UserDefaultAttrProp()
        aprop.set_label("%s/State" % (devName))
        dynAttr = PyTango.Attr(dynAttrName, PyTango.CmdArgType.DevState,
                               PyTango.READ)
        dynAttr.set_default_properties(aprop)
        self.add_attribute(dynAttr,
                           r_meth=Watchdog.read_oneDeviceState,
                           is_allo_meth=Watchdog.is_oneDeviceState_allowed)
        self.set_change_event(dynAttrName, True, False)
        self.debug_stream("In %s::_build_WatchedStateAttribute() "
                          "add dyn_attr %s" % (self.get_name(), dynAttrName))

    def _prepare_ExtraAttrs(self):
        extraAttrs = []
        for i in range(len(self.ExtraAttrList)):
            subline = self.ExtraAttrList[i].split(',')
            for j in range(len(subline)):
                if len(subline[j]) > 0:
                    try:
                        attrName = subline[j].lower()
                        extraAttrs.append(attrName)
                    except Exception as e:
                        errMsg = "In %s::_prepare_ExtraAttrs() "\
                                 "Exception in ExtraAttrList processing: "\
                                 "%d line, %d element, exception: %s"\
                                 % (self.get_name(), i, j, str(e))
                        self.error_stream(errMsg)
                        traceback.print_exc()
        return extraAttrs

    def _build_ExtraAttrs(self, devName, attrsLst):
        for attrName in attrsLst:
            self._build_ExtraAttr(devName, attrName)

    def _build_ExtraAttr(self, devName, attrName):
        fullAttrName = "%s/%s" % (devName, attrName)
        try:
            attrCfg = PyTango.AttributeProxy(fullAttrName).get_config()
            dynAttrName = "%s" % (fullAttrName.replace("/", SEPARATOR))
            if attrCfg.data_format == PyTango.AttrDataFormat.SCALAR:
                aprop = PyTango.UserDefaultAttrProp()
                aprop.set_label(fullAttrName)
                dynAttr = PyTango.Attr(dynAttrName, attrCfg.data_type,
                                       attrCfg.writable)
                dynAttr.set_default_properties(aprop)
                if attrCfg.writable == PyTango.AttrWriteType.READ_WRITE:
                    w_meth = Watchdog.write_ExtraAttribute
                else:
                    w_meth = None
                is_allowed = Watchdog.is_ExtraAttribute_allowed
                self.add_attribute(dynAttr,
                                   r_meth=Watchdog.read_ExtraAttribute,
                                   w_meth=w_meth,
                                   is_allo_meth=is_allowed)
                self.set_change_event(dynAttrName, True, False)
            else:
                raise Exception("Not yet supported array attributes")
            return attrCfg.data_type
        except Exception as e:
            errMsg = "In %s::_build_ExtraAttr() "\
                     "Exception in ExtraAttrList processing: "\
                     "%s, exception: %s"\
                     % (self.get_name(), fullAttrName, str(e))
            self.error_stream(errMsg)
            traceback.print_exc()

    # Done Process Properties ---
    #############################

    ######################
    # # dyn_attr region ---
    def read_oneDeviceState(self, attr):
#         self.debug_stream("In %s::read_oneDeviceState()" % (self.get_name()))
        try:
            attrFullName = attr.get_name().replace(SEPARATOR, "/")
            devName, _ = attrFullName.rsplit('/', 1)
        except:
            self.error_stream("In %s::read_oneDeviceState() cannot extract "
                              "the name from %s"
                              % (self.get_name(), attr.get_name()))
            attr.set_value(PyTango.DevState.UNKNOWN)
            return
        try:
            state = self.DevicesDict[devName].devState
            if not state:
                state = PyTango.DevState.UNKNOWN
            if state:
                attr.set_value(state)
            else:
                attr.set_value_date_quality(PyTango.DevState.UNKNOWN, time(),
                                            PyTango.AttrQuality.ATTR_INVALID)
        except Exception as e:
            self.error_stream("In %s::read_oneDeviceState() Exception with "
                              "%s reading the state: %s"
                              % (self.get_name(), devName, e))
            attr.set_value(PyTango.DevState.UNKNOWN)

    def is_oneDeviceState_allowed(self, req_type):
        if self.get_state() in [PyTango.DevState.FAULT]:
            #    End of Generated Code
            #    Re-Start of Generated Code
            return False
        return True

    def read_ExtraAttribute(self, attr):
        devName, attrName = self._recoverDevAttrName(attr)
#         self.debug_stream("In %s::read_ExtraAttribute(): %s/%s"
#                           % (self.get_name(), devName, attrName))
        value = self.DevicesDict[devName].getExtraAttr(attrName)
        if value is not None:
            attr.set_value(value)
        else:
            try:
                attr.set_value_date_quality(0, time(),
                                            PyTango.AttrQuality.ATTR_INVALID)
            except:
                attr.set_value_date_quality("", time(),
                                            PyTango.AttrQuality.ATTR_INVALID)

    def write_ExtraAttribute(self, attr):
        devName, attrName = self._recoverDevAttrName(attr)
        data = []
        attr.get_write_value(data)
        value = data[0]
        self.debug_stream("In %s::write_ExtraAttribute(): %s/%s = %s"
                          % (self.get_name(), devName, attrName, value))
        self.DevicesDict[devName].setExtraAttr(attrName, value)

    def is_ExtraAttribute_allowed(self, req_type):
        if self.get_state() in [PyTango.DevState.FAULT]:
            #    End of Generated Code
            #    Re-Start of Generated Code
            return False
        return True

    def _recoverDevAttrName(self, attr):
        try:
            attrFullName = attr.get_name().replace(SEPARATOR, "/")
            devName, attrName = attrFullName.rsplit('/', 1)
        except:
            self.error_stream("In %s::_recoverDevAttrName() cannot extract "
                              "the name from %s"
                              % (self.get_name(), attr.get_name()))
            devName, attrName = None, None
        return devName, attrName

    def read_Dealer(self, attr):
        if not self._dealer:
            attr.set_value('')
        else:
            attr.set_value(self._dealer.type())

    def write_Dealer(self, attr=None):
        data = []
        attr.get_write_value(data)
        value = data[0]
        if self._dealer and value in self._dealer.types():
            self._rebuildDealer(value)

    def read_Dealers(self, attr):
        if not self._dealer:
            attr.set_value([''])
        else:
            attr.set_value(self._dealer.types())

    def _readAllDevNames(self, attr):
        attr.set_value(self._allDevices)

    def _readAllExtraAttrs(self, attr):
        attr.set_value(self._extraAttrs)

    def _readExtraAttrLst(self, attr):
        attrName = attr.get_name()
        attrType = attr.get_data_type()
        values = []
        self.info_stream("collecting %s" % (attrName))
        for devName in self._allDevices:
            value = self.DevicesDict[devName].getExtraAttr(attrName)
            if value is None:
                if attrType in [PyTango.DevString]:
                    value = ''
                elif attrType in [PyTango.DevFloat, PyTango.DevDouble]:
                    value = float('nan')
                else:  # if attrType in [PyTango.DevShort, PyTango.DevLong]:
                    value = 0
            self.info_stream("\tdevice %s: %s" % (devName, value))
            values.append(value)
        attr.set_value(values)

    # TODO: more dynamic attributes:
    #       - allow to adjust the {Fault,Hand}Recovery for each of the watched
    #         (remember to make them memorised).
    #       - allow to adjust the recheck period for each of the watched
    #       - report threshold for running devices

    # Done dyn_attr region ---
    ##########################

    ####################
    # # events region ---
    def fireEventsList(self, eventsAttrList):
        timestamp = time()
        attrNames = []
        for attrEvent in eventsAttrList:
            try:
                attrName = attrEvent[0]
                attrValue = attrEvent[1]
                attrNames.append(attrName)
                if len(attrEvent) == 3:  # specifies quality
                    attrQuality = attrEvent[2]
                else:
                    attrQuality = PyTango.AttrQuality.ATTR_VALID
                self.push_change_event(attrName, attrValue,
                                       timestamp, attrQuality)
                self.debug_stream("In %s::fireEventsList() attribute: %s, "
                                  "value: %s (quality %s, timestamp %s)"
                                  % (self.get_name(), attrName,
                                     str(attrValue), str(attrQuality),
                                     str(timestamp)))
            except Exception as e:
                self.error_stream("In %s::fireEventsList() Exception "
                                  "with attribute %s:\n%s"
                                  % (self.get_name(), attrEvent[0], e))
        if len(attrNames) > 0:
            self.debug_stream("In %s::fireEventsList() emitted %d events: %s"
                              % (self.get_name(), len(attrNames), attrNames))
    # Done events region ---
    ########################

    ################
    # Dog region ---
    def isInRunningLst(self, who):
        return self.isInLst(self.attr_RunningDevicesList_read, who)

    def appendToRunning(self, who):
        if self.appendToLst(self.attr_RunningDevicesList_read, "Running", who):
            self.fireRunningAttrEvents()
            if self._dealer:
                self._dealer.distribute()

    def removeFromRunning(self, who):
        if self.removeFromLst(self.attr_RunningDevicesList_read, "Running",
                              who):
            self.fireRunningAttrEvents()
            if self._dealer:
                self._dealer.distribute()

    def fireRunningAttrEvents(self):
        devLst = self.attr_RunningDevicesList_read[:]
        howManyNow = len(devLst)
        if self.attr_RunningDevices_read != howManyNow:
            self.attr_RunningDevices_read = howManyNow
            self._collect("RUNNING", howManyNow, devLst)
        self.fireEventsList([["RunningDevices", howManyNow],
                             ["RunningDevicesList", devLst]])

    def isInFaultLst(self, who):
        return self.isInLst(self.attr_FaultDevicesList_read, who)

    def appendToFault(self, who):
        if self.appendToLst(self.attr_FaultDevicesList_read, "Fault", who):
            self.fireFaultAttrEvents()

    def removeFromFault(self, who):
        if self.removeFromLst(self.attr_FaultDevicesList_read, "Fault", who):
            self.fireFaultAttrEvents()

    def fireFaultAttrEvents(self):
        devLst = self.attr_FaultDevicesList_read[:]
        howManyNow = len(devLst)
        if self.attr_FaultDevices_read != howManyNow:
            self.attr_FaultDevices_read = howManyNow
            self._report("FAULT", howManyNow, devLst)
        self.fireEventsList([["FaultDevices", howManyNow],
                             ["FaultDevicesList", devLst]])

    def isInHangLst(self, who):
        return self.isInLst(self.attr_HangDevicesList_read, who)

    def appendToHang(self, who):
        if self.appendToLst(self.attr_HangDevicesList_read, "Hang", who):
            self.fireHangAttrEvents()

    def removeFromHang(self, who):
        if self.removeFromLst(self.attr_HangDevicesList_read, "Hang", who):
            self.fireHangAttrEvents()

    def fireHangAttrEvents(self):
        devLst = self.attr_HangDevicesList_read[:]
        howManyNow = len(devLst)
        if self.attr_HangDevices_read != howManyNow:
            self.attr_HangDevices_read = howManyNow
            self._report("HANG", howManyNow, devLst)
        self.fireEventsList([["HangDevices", howManyNow],
                             ["HangDevicesList", devLst]])

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
            name = self.get_name()  # .replace("/", SEPARATOR)
            mail = email.mime.text.MIMEText(msg)
            mail['From'] = "%s@%s" % (name, gethostname())
            mail['To'] = ', '.join(self.MailTo)
            mail['Subject'] = "[%s] %s" % (self.get_name(), action)
            s = smtplib.SMTP('localhost')
            s.sendmail(mail['From'], self.MailTo, mail.as_string())
            s.quit()
            self.debug_stream("Email sent... (%s)" % (mail['To']))

    def _report(self, action, howmany, lst):
        subject = "Watchdog %s report" % action
        mailBody = "Status Report from the watchdog %s\n"\
            % (self.get_name())
        mailBody = "%s%s devices change to %d\n%s"\
            % (mailBody, action, howmany, lst)
        mailBody = "%s\n--\nEnd transmission." % (mailBody)
        self.mailto(subject, mailBody)
        self._collect(action, howmany, lst)

    def _prepareCollectorThread(self):
        if self._changesCollector is None:
            try:
                self.ReportPeriod = int(self.ReportPeriod)*60*60  # h to s
            except:
                self.ReportPeriod = COLLECTION_REPORT_PERIOD
            self.debug_stream("Setting the periodic report period to %sh"
                              % (self.ReportPeriod/60/60))
            self._lastCollection = time()
            self._changesCollector = Thread(target=self._collectionReporter)
            self._changesCollector.setDaemon(True)
            self._changesCollector.start()
            self.debug_stream("Collector thread launched")

    def _collect(self, action, howmany, lst):
        try:
            with self._changesCollectorLock:
                if action not in self._changesDct:
                    self._changesDct[action] = {}
                now = ctime()
                while now in self._changesDct[action]:
                    now += "."  # if many in the same second, tag them
                self._changesDct[action][now] = [howmany, lst]
            self.debug_stream("Collected %s information: %d and %s"
                              % (action, howmany, lst))
        except Exception as e:
            self.error_stream("Exception collecting %s information: %s"
                              % (action, e))

    def _collectionReporter(self):
        self.debug_stream("Collector thread says hello. "
                          "First report in %d seconds" % (self.ReportPeriod))
        sleep(self.ReportPeriod)
        while not self._joinerEvent.isSet():
            t0 = time()
            self.debug_stream("Collector thread starts reporting process")
            if self._doCollectorReport():
                self._changesDct = {}
            t_diff = time()-t0
            if not self._joinerEvent.isSet():
                next = self.ReportPeriod-t_diff
                self.debug_stream("Next report in %d seconds" % next)
                sleep(next)

    def _doCollectorReport(self):
        subject = "Watchdog periodic report"
        try:
            avoidSend = True  # do not send if there is nothing to send
            mailBody = "Status Report since %s of watchdog %s\n\n"\
                % (ctime(self._lastCollection), self.get_name())
            with self._changesCollectorLock:
                if len(self._changesDct.keys()) > 0:
                    avoidSend = False  # there is something to be reported
                    for action in self._changesDct.keys():
                        mailBody = "%sCollected events for action %s\n"\
                            % (mailBody, action)
                        whenLst = self._changesDct[action].keys()
                        whenLst.sort()
                        for when in whenLst:
                            howmany, lst = self._changesDct[action][when]
                            mailBody = "%s\tat %s: %d devices\n"\
                                % (mailBody, when, howmany)
                            lst.sort()
                            for each in lst:
                                mailBody = "%s\t\t%s\n" % (mailBody, each)
                    self._lastCollection = time()
            mailBody = "%s\n--\nEnd transmission." % (mailBody)
            if not avoidSend:
                self.mailto(subject, mailBody)
            return True
        except Exception as e:
            self.error_stream("Exception reporting collected information"
                              ": %s" % (e))
            traceback.print_exc()
            try:
                subject = "Report exception"
                mailBody = ""
                self.mailto(subject, mailBody)
            except Exception as e2:
                self.error_stream("Not reported the first exception, because"
                                  "another in email send: %s" % (e2))
                traceback.print_exc()
            return False
    # Done dog region ---
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
        self._changesCollector = None
        self._changesDct = {}
        self._changesCollectorLock = Lock()
        self._prepareCollectorThread()
        self._dealer = None
        self._allDevices = []
        self._processDevicesListProperty()
        # everything ok:
        self.change_state(PyTango.DevState.ON)

    def always_executed_hook(self):
#         self.debug_stream("In always_excuted_hook()")
        pass

    # -------------------------------------------------------------------------
    #    Watchdog read/write attribute methods
    # -------------------------------------------------------------------------
    def read_RunningDevices(self, attr):
#         self.debug_stream("In read_RunningDevices()")
        attr.set_value(self.attr_RunningDevices_read)

    def read_FaultDevices(self, attr):
#         self.debug_stream("In read_FaultDevices()")
        attr.set_value(self.attr_FaultDevices_read)

    def read_HangDevices(self, attr):
#         self.debug_stream("In read_HangDevices()")
        attr.set_value(self.attr_HangDevices_read)

    def read_RunningDevicesList(self, attr):
#         self.debug_stream("In read_RunningDevicesList()")
        attr.set_value(self.attr_RunningDevicesList_read)

    def read_FaultDevicesList(self, attr):
#         self.debug_stream("In read_FaultDevicesList()")
        attr.set_value(self.attr_FaultDevicesList_read)

    def read_HangDevicesList(self, attr):
#         self.debug_stream("In read_HangDevicesList()")
        attr.set_value(self.attr_HangDevicesList_read)

    def initialize_dynamic_attributes(self):
        pass

    def read_attr_hardware(self, data):
#         self.debug_stream("In read_attr_hardware()")
        pass


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
             "List of string with the name of the devices to be watched.",
             []],
        'ExtraAttrList':
            [PyTango.DevVarStringArray,
             "For each of the devices watched, if exist, build attribute "
             "mirrors ",
             []],
        'DealerAttrList':
            [PyTango.DevVarStringArray,
             "Attributes that the dealer will balance",
             []],
#         'DeviceGroups':
#             [PyTango.DevVarStringArray,
#              "Dictionary with list in the items similar to the DeviceList "
#              "but classifying the devices in groups using the keys.",
#              []],
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
             []],
        'ReportPeriod':
            [PyTango.DevUShort,
             "Hours between periodic reports",
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
