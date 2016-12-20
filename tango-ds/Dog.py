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

__all__ = ["Logger", "Dog", "WatchdogTester", "main"]
__docformat__ = 'restructuredtext'

try:
    from fandango import Astor  # soft dependency
except:
    Astor = None
import email.mime.text
import smtplib
from socket import gethostname
from PyTango import DeviceProxy, DevState, EventType, DevFailed
from time import sleep, time
from threading import Thread, Event
import traceback


DEFAULT_RECHECK_TIME = 180.0  # seconds
DEFAULT_nOVERLAPS_ALERT = 10
DEFAULT_ASTOR_nSTOPS = 2
DEFAULT_ASTOR_STOPWAIT = 3  # seconds
SEPARATOR = "\\"


class Logger(object):
    def __init__(self, parent, *args, **kwargs):
        super(Logger, self).__init__(*args, **kwargs)
        self._parent = parent
        # --- tango streams
        self.error_stream = parent.error_stream
        self.warn_stream = parent.warn_stream
        self.info_stream = parent.info_stream
        self.debug_stream = parent.debug_stream
        # --- tango event retransmission
        self.fireEventsList = parent.fireEventsList
        # --- running
        self.isInRunningLst = parent.isInRunningLst
        self.appendToRunning = parent.appendToRunning
        self.removeFromRunning = parent.removeFromRunning
        # --- fault
        self.isInFaultLst = parent.isInFaultLst
        self.appendToFault = parent.appendToFault
        self.removeFromFault = parent.removeFromFault
        # --- hang
        self.isInHangLst = parent.isInHangLst
        self.appendToHang = parent.appendToHang
        self.removeFromHang = parent.removeFromHang
        # --- mailto
        self.mailto = parent.mailto

    def fireEvent(self, attrName, value, timestamp=None, quality=None):
        attrFullName = "%s%s%s"\
            % (self.devName.replace("/", SEPARATOR), SEPARATOR, attrName)
        try:
            if timestamp and quality:
                self.fireEventsList([[attrFullName, value, timestamp,
                                      quality]])
            else:
                self.fireEventsList([[attrFullName, value]])
        except Exception as e:
            self.error_stream("Cannot fire event for %s/%s: %s"
                              % (self.devName, attrName, e))
            traceback.print_exc()


class Dog(Logger):
    def __init__(self, devName, joinerEvent=None, startDelay=None,
                 extraAttrs=None, *args, **kwargs):
        super(Dog, self).__init__(*args, **kwargs)
        self._devName = devName
        self._devProxy = None
        self._eventId = None
        self._devState = None
        # --- fault vbles
        self._tryFaultRecovery = False
        self._faultRecoveryCtr = 0
        self._devStatus = None
        # --- hangVbles
        self._tryHangRecovery = False
        self._hangRecoveryCtr = 0
        # --- Thread for hang monitoring
        self._joinerEvent = joinerEvent
        self._thread = None
        self._recheckPeriod = DEFAULT_RECHECK_TIME
        self._overlaps = 0
        self._overlapsAlert = DEFAULT_nOVERLAPS_ALERT
        # --- extra attributes
        self._extraAttributes = []
        self._extraEventIds = {}
        self._extraAttrValues = {}
        for attrName in extraAttrs:
            attrName = attrName.lower()
            self._extraAttributes.append(attrName)
            self._extraEventIds[attrName] = None
            self._extraAttrValues[attrName] = None
        # --- build proxy and event subscriptions
        self.__buildProxy()
        self.__createThread(startDelay)

    def __str__(self):
        return "Dog(%s, state=%s)" % (self.devName, self.devState)

    def __repr__(self):
        return "Dog(%s, state=%s, faultRecovery=%s, hangRecovery=%s)"\
            % (self.devName, self.devState, self.tryFaultRecovery,
               self.tryHangRecovery)

    # --- object properties

    @property
    def devName(self):
        return self._devName

    @property
    def devProxy(self):
        return self._devProxy

    @property
    def devState(self):
        return self._devState

    def getExtraAttr(self, attrName):
        try:
            value = self._devProxy[attrName].value
            timestamp = self._devProxy[attrName].time.totime()
            quality = self._devProxy[attrName].quality
            if value != self._extraAttrValues[attrName]:
                self.debug_stream("%s/%s has changed from %s to %s"
                                  % (self.devName, attrName,
                                     self._extraAttrValues[attrName], value))
                self._extraAttrValues[attrName] = value
                self.fireEvent(attrName, value, timestamp, quality)
            return value
        except DevFailed as e:
            self.warn_stream("%s/%s read exception: %s"
                             % (self.devName, attrName, e[0].desc))
        except Exception as e:
            self.error_stream("%s/%s read exception: %s"
                              % (self.devName, attrName, e))
            raise Exception("%s/%s cannot be read" % (self.devname, attrName))

    def setExtraAttr(self, attrName, value):
        try:
            self._devProxy[attrName] = value
        except Exception as e:
            self.error_stream("%s/%s write exception: %s"
                              % (self.devName, attrName, e))
            raise Exception("%s/%s cannot be write" % (self.devname, attrName))

    @property
    def tryFaultRecovery(self):
        return self._tryFaultRecovery

    @tryFaultRecovery.setter
    def tryFaultRecovery(self, value):
        if type(value) == bool:
            self._tryFaultRecovery = value
        else:
            self.error_stream("Only boolean assignment")

    @property
    def tryHangRecovery(self):
        return self._tryHangRecovery

    @tryFaultRecovery.setter
    def tryHangRecovery(self, value):
        if type(value) == bool:
            if value and not Astor:
                self.error_stream("This feature is only available with "
                                  "fandango's Astor present")
                return
            self._tryHangRecovery = value
        else:
            self.error_stream("Only boolean assignment")

    @property
    def recheckPeriod(self):
        return self._recheckPeriod

    @property
    def overlapsAlert(self):
        return self._overlapsAlert

    # --- Constructor methods

    def __buildProxy(self):
        try:
            self._devProxy = DeviceProxy(self._devName)
            self.__subscribe_event()
        except Exception as e:
            self.error_stream("%s proxy not available: %s"
                              % (self._devName, e))
            self.appendToHang(self.devName)

    def __subscribe_event(self):
        self._eventId = \
            self._devProxy.subscribe_event('State',
                                           EventType.CHANGE_EVENT,
                                           self)
        self.info_stream("Subscribed to %s/State (id=%d)"
                         % (self.devName, self._eventId))
        self.__subscribe_extraAttrs()

    def __unsubscribe_event(self):
        if self._eventId:
            try:
                self._devProxy.unsubscribe_event(self._eventId)
            except Exception as e:
                self.error_stream("%s failed to unsubscribe event: %s"
                                  % (self.devName, e))
            self._eventId = None
        else:
            self.warn_stream("%s no event id to unsubscribe." % (self.devName))
        self.__unsubscribe_extraAttrs()

    def __subscribe_extraAttrs(self):
        for attrName in self._extraAttributes:
            try:
                self._extraEventIds[attrName] = \
                    self._devProxy.subscribe_event(attrName,
                                                   EventType.CHANGE_EVENT,
                                                   self)
                self.info_stream("Subscribed to %s/%s (id=%d)"
                                 % (self.devName, attrName,
                                    self._extraEventIds[attrName]))
            except DevFailed as e:
                self.warn_stream("%s/%s failed to subscribe event: %s"
                                 % (self.devName, attrName, e[0].desc))
            except Exception as e:
                self.error_stream("%s/%s failed to subscribe event: %s"
                                  % (self.devName, attrName, e))

    def __unsubscribe_extraAttrs(self):
        for attrName in self._extraEventIds.keys():
            if self._extraEventIds[attrName]:
                try:
                    self._devProxy.\
                        unsubscribe_event(self._extraEventIds[attrName])
                except Exception as e:
                    self.error_stream("%s/%s failed to unsubscribe event: %s"
                                      % (self.devName, attrName, e))
                self._extraEventIds[attrName] = None
            else:
                self.warn_stream("%s/%s no event id to unsubscribe."
                                 % (self.devName, attrName))

    def __createThread(self, startDelay):
        try:
            self._thread = Thread(target=self.__hangMonitorThread,
                                  args=(startDelay,))
            self._thread.setDaemon(True)
            if startDelay > 0:
                self.info_stream("Monitor %s will wait %g seconds until "
                                 "thread start" % (self.devName, startDelay))
            else:
                self.info_stream("Monitor %s will start the thread "
                                 "immediately" % (self.devName))
            self._thread.start()
        except Exception as e:
            self.error_stream("%s hang monitor thread creation fail: %s"
                              % (self.devName, e))
            traceback.print_exc()

    # --- Events

    def push_event(self, event):
        try:
            if event is None:
                return
            if not hasattr(event, 'attr_value') or event.attr_value is None \
                    or event.attr_value.value is None:
                # self.debug_stream("%s push_event() %s: value has None type"
                #                   %(self.devName, event.attr_name))
                return
            # ---FIXME: Ugly!! but it comes with a fullname
            nameSplit = event.attr_name.rsplit('/', 4)[1:5]
            domain, family, member, attrName = nameSplit
            devName = "%s/%s/%s" % (domain, family, member)
            attrName = attrName.lower()
            if devName != self.devName:
                self.error_stream("Event received doesn't correspond with "
                                  "who the listener expects (%s != %s)"
                                  % (devName, self.devName))
                return
            # ---
            if attrName == 'state':
                self.debug_stream("%s push_event() value = %s"
                                  % (self.devName, event.attr_value.value))
                self.__checkDeviceState(event.attr_value.value)
                self.fireEvent('State', event.attr_value.value)
            elif attrName in self._extraAttributes:
                self.debug_stream("%s/%s push_event() value = %s"
                                  % (self.devName, attrName,
                                     event.attr_value.value))
                self.fireEvent(attrName, event.attr_value.value)
                self._extraAttrValues[attrName] = event.attr_value.value
            else:
                self.warn_stream("%s/%s push_event() unmanaged attribute "
                                 "(value = %s)" % (self.devName, attrName,
                                                   event.attr_value.value))
        except Exception as e:
            self.debug_stream("%s push_event() Exception %s"
                              % (self.devName, e))
            traceback.print_exc()

    # --- checks

    def __checkDeviceState(self, newState=None):
        if self.__stateHasChange(newState):
            self.debug_stream("%s state change from %s to %s"
                              % (self.devName, self._devState, newState))
            # state change to one of the lists
            if newState is DevState.RUNNING:
                self.appendToRunning(self.devName)
            elif newState is DevState.FAULT:
                self.appendToFault(self.devName)
            # state change from one of the lists
            elif self.__wasRunning():
                self.removeFromRunning(self.devName)
            elif self.__wasInFault():
                self.removeFromFault(self.devName)
                self._faultRecoveryCtr = 0
            # recover from Hang
            if self.devState is None:
                if self.isInHangLst(self.devName):
                    self.debug_stream("%s received state information after "
                                      "hang, remove from the list."
                                      % (self.devName))
                    self.removeFromHang(self.devName)
                    self._hangRecoveryCtr = 0
            self._devState = newState
            self.debug_stream("%s store newer state %s"
                              % (self.devName, self.devState))
        # else: nothing change, nothing to do.

    def __stateHasChange(self, newState):
        return newState != self.devState

    def __wasRunning(self):
        return self.devState == DevState.RUNNING

    def __wasInFault(self):
        return self.devState == DevState.FAULT

    # --- threading

    def __hangMonitorThread(self, startDelay):
        if startDelay > 0:
            self.info_stream("%s watchdog build, wait %g until start"
                             % (self.devName, startDelay))
            sleep(startDelay)
        self.info_stream("%s launch background monitor" % (self.devName))
        while not self._joinerEvent.isSet():
            t_0 = time()
            self.__manualCheck()
            self.__waitNextCheck(time()-t_0)

    def __manualCheck(self):
        for i in range(2):
            state = self.__stateRequest()
            if state:
                self.info_stream("%s respond state %s" % (self.devName, state))
                break
        if not state:  # no answer from the device
            if not self.isInHangLst(self.devName):
                self.debug_stream("%s no state information." % (self.devName))
                self.__unsubscribe_event()
                self.appendToHang(self.devName)
            # review any other list where it can be
            if self.isInRunningLst(self.devName):
                self.removeFromRunning(self.devName)
            if self.isInFaultLst(self.devName):
                self.removeFromFault(self.devName)
                self._faultRecoveryCtr = 0
            if self.devState is None and self.tryHangRecovery:
                self.debug_stream("%s not state information by a second try."
                                  % (self.devName))
                # force to launch the recover after a second loop
                self.__hangRecoveryProcedure()
            self._devState = None
        else:
            if self.devState is None:
                self.debug_stream("%s gives state information, back from hang."
                                  % (self.devName))
                if self.isInHangLst(self.devName):
                    self.removeFromHang(self.devName)
                    self._hangRecoveryCtr = 0
                self._devState = state
                self.__buildProxy()
            if state == DevState.FAULT and self.tryFaultRecovery:
                self.__faultRecoveryProcedure()
            if self.devState != state:
                # state has change but hasn't been cached by events
                self._devState = state

    def __stateRequest(self):
        try:
            return self.devProxy.State()
        except:
            self.warn_stream("%s don't respond state request" % (self.devName))
            return None

    def __waitNextCheck(self, deltaT):
        if deltaT < self._recheckPeriod:
            toSleep = self._recheckPeriod-deltaT
            self.debug_stream("%s monitor's thread required %g seconds"
                              "(go sleep for %g seconds)"
                              % (self.devName, deltaT, toSleep))
            self._overlaps = 0
            sleep(toSleep)
        else:
            self._overlaps += 1
            if self._overlaps % self._overlapsAlert:
                self.warn_stream("%s hang check has take more than loop time "
                                 "(%g seconds). No sleep for another check."
                                 % (self.devName, deltaT))
            else:  # when modulo self._overlapsAlert == 0
                self.warn_stream("%s hang check has take more than loop time "
                                 "(%g seconds). But %d consecutive, forcing "
                                 "to sleep some time."
                                 % (self.devName, deltaT, self._overlaps))
                self.mailto("Recheck overlaps", "There has been %d "
                            "consecutive overlaps in the recheck thread"
                            % (self._recheckLoopOverlaps))
                sleep(self._recheckPeriod)

    def __faultRecoveryProcedure(self):
        statusMsg = None
        try:
            if self._devProxy:
                statusMsg = self._devProxy.status()
                self._devProxy.Init()
            else:
                self.warn_stream("%s no proxy to command Init()"
                                 % (self.devName))
        except Exception as exceptionObj:
            self.error_stream("%s in Fault recovery procedure Exception: %s"
                              % (self.devName, e))
        else:
            self.info_stream("%s Init() completed" % (self.devName))
            exceptionObj = None
        self._reportFaultProcedure(exceptionObj, statusMsg)
        self._faultRecoveryCtr += 1

    def __hangRecoveryProcedure(self):
        try:
            astor = Astor()
            instance = astor.get_device_server(self.devName)
            if not instance:
                raise Exception("Astor didn't solve the "
                                "device server instance (%s)" % instance)
            if not self.__forceRestartInstance(astor, instance):
                self.error_stream("%s Astor cannot recover" % (self.devName))
        except Exception as exceptionObj:
            self.error_stream("%s __hangRecoveryProcedure() Exception %s"
                              % (self.devName, exceptionObj))
        else:
            exceptionObj = None
        self._reportHangProcedure(instance, exceptionObj)
        self._hangRecoveryCtr += 1

    def __forceRestartInstance(self, astor, instance):
        for i in range(DEFAULT_ASTOR_nSTOPS):
            res = astor.stop_servers([instance])
            if res:
                break
            sleep(DEFAULT_ASTOR_STOPWAIT)
        self.info_stream("%s Astor start %s" % (self.devName, instance))
        return astor.start_servers([instance])

    def _reportFaultProcedure(self, exceptionObj, statusMsg):
        if self._faultRecoveryCtr == 0:
            # only report when it has happen, no remainders
            mailBody = "Applied the recovery from Fault procedure.\n"
            mailBody = "%s\nAffected camera was: %s" % (mailBody, self.devName)
            if exceptionObj:
                mailBody = "%s\nEncoutered exceptions during the process:\n%s"\
                           % (mailBody, exceptionObj)
            if statusMsg:
                mailBody = "%s\n\nStatus before the Init(): %s"\
                    % (mailBody, statusMsg)
                self._devStatus = statusMsg
            mailBody = "%s\n--\nEnd transmission." % (mailBody)
            # self.mailto("Device in FAULT state", mailBody)

    def _reportHangProcedure(self, instance, exceptionObj):
        if self._hangRecoveryCtr == 0:
            # only report when it has happen, no remainders
            mailBody = "Applied the recovery from Hang procedure.\n"
            mailBody = "%s\nAffected camera was: %s" % (mailBody, self.devName)
            if instance:
                mailBody = "%s (instance: %s)" % (mailBody, instance)
            if exceptionObj:
                mailBody = "%s\nEncoutered exceptions during the process:\n%s"\
                    % (mailBody, exceptionObj)
            mailBody = "%s\n--\nEnd transmission." % (mailBody)
            # self.mailto("Device HANG", mailBody)


class WatchdogTester(object):
    def __init__(self, deviceLst, joinerEvent, *args, **kwargs):
        super(WatchdogTester, self).__init__(*args, **kwargs)
        self._monitorsLst = []
        self._runningLst = []
        self._faultLst = []
        self._hangLst = []
        for deviceName in deviceLst:
            dog = Dog(deviceName, joinerEvent, self)
            dog.tryFaultRecovery = True
            dog.tryHangRecovery = True
            self._monitorsLst.append(dog)

    def error_stream(self, msg):
        print("ERROR:\t%s" % msg)

    def warn_stream(self, msg):
        print("WARN:\t%s" % msg)

    def info_stream(self, msg):
        print("INFO:\t%s" % msg)

    def debug_stream(self, msg):
        print("DEBUG:\t%s" % msg)

    def isInRunningLst(self, who):
        self.isInLst(self._runningLst, who)

    def appendToRunning(self, who):
        self.appendToLst(self._runningLst, "running", who)

    def removeFromRunning(self, who):
        self.removeFromLst(self._runningLst, "running", who)

    def isInFaultLst(self, who):
        self.isInLst(self._faultLst, who)

    def appendToFault(self, who):
        self.appendToLst(self._faultLst, "fault", who)

    def removeFromFault(self, who):
        self.removeFromLst(self._faultLst, "fault", who)

    def isInHangLst(self, who):
        self.isInLst(self._hangLst, who)

    def appendToHang(self, who):
        self.appendToLst(self._hangLst, "hang", who)

    def removeFromHang(self, who):
        self.removeFromLst(self._hangLst, "hang", who)

    def isInLst(self, lst, who):
        return lst.count(who)

    def appendToLst(self, lst, lstName, who):
        if not lst.count(who):
            lst.append(who)
            self.info_stream("%s append to %s list" % (who, lstName))
        else:
            self.warn_stream("%s was already in the %s list" % (who, lstName))

    def removeFromLst(self, lst, lstName, who):
        if lst.count(who):
            lst.pop(lst.index(who))
            self.info_stream("%s removed from %s list" % (who, lstName))
        else:
            self.warn_stream("%s was NOT in the %s list" % (who, lstName))

    def mailto(self, action, msg):
        if len(self.MailTo) != 0:
            name = self.get_name()
            mail = email.mime.text.MIMEText(msg)
            mail['From'] = "%s@%s" % (name, gethostname())
            mail['To'] = ', '.join(self.MailTo)
            mail['Subject'] = "[%s] %s" % (self.get_name(), action)
            s = smtplib.SMTP('localhost')
            s.sendmail(mail['From'], self.MailTo, mail.as_string())
            s.quit()
            self.debug_stream("Email sent...")


def main():
    from optparse import OptionParser
    import signal
    import sys

    def signal_handler(signal, frame):
        print('\nYou pressed Ctrl+C!\n')
        sys.exit(0)

    parser = OptionParser()
    parser.add_option('', "--devices",
                      help="List of device names to provide to the tester")
    (options, args) = parser.parse_args()
    if options.devices:
        signal.signal(signal.SIGINT, signal_handler)
        print("\n\tPress Ctrl+C to finish\n")
        joinerEvent = Event()
        joinerEvent.clear()
        tester = WatchdogTester(options.devices.split(','), joinerEvent)
        signal.pause()
        del tester

if __name__ == '__main__':
    main()
