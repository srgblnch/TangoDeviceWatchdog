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

from dog import Logger, Dog
from numpy import linspace
from PyTango import DevState


class Dealer(Logger):
    def __init__(self, attrLst, dogsLst, statesLst=None,
                 *args, **kwargs):
        super(Dealer, self).__init__(*args, **kwargs)
#         self.__attrLst = None
#         self.__dogs = None
#         self.__states = None
        self._setDogsLst(dogsLst)
        self._setStatesLst(statesLst)
        self._setAttrLst(attrLst)

    def _setDogsLst(self, dogsLst):
        if all([type(dog) is Dog for dog in dogsLst]):
            self.__dogs = dogsLst
        else:
            raise AssertionError("Cannot manage the list of dogs %s"
                                 % (dogsLst))

    def _setStatesLst(self, statesLst):
        if statesLst is None:
            self.__states = [DevState.RUNNING]
        elif type(statesLst) is list and\
                all([x in DevState.values.values() for x in statesLst]):
            self.__states = statesLst
        else:
            raise AssertionError("Cannot manage the list of states %s"
                                 % (statesLst))

    def _setAttrLst(self, attrLst):
        if type(attrLst) is list:
            self.__attrLst = []
            for attrName in attrLst:
                if all([dog.hasExtraAttr(attrName) for dog in self.__dogs]):
                    self.__attrLst.append(attrName)
                else:
                    raise AssertionError("Not all the dogs have the attribute "
                                         "%s" % attrName)
        else:
            raise AssertionError("attrLst must be a list")

    @property
    def attrLst(self):
        return self.__attrLst

    def pairOfAttrs(self):
        i = 0
        while i < len(self.__attrLst):
            first = self.__attrLst[i]
            if i+1 < len(self.__attrLst):
                second = self.__attrLst[i+1]
            else:
                second = None
            yield [first, second]
            i += 2

    @property
    def attrValues(self):
        answer = {}
        for dog in self.__dogs:
            try:
                answer[dog.devName] = dog.getExtraAttr(self.__attrName)
            except Exception as e:
                self.warn_stream("Cannot read the %s/%s value"
                                 % (dog.devName, self.__attrName))
                answer[dog.devName] = None
        return answer

    @property
    def devStates(self):
        answer = {}
        for dog in self.__dogs:
            answer[dog.devName] = dog.devState
        return answer

    @property
    def candidates(self):
        candidates = []
        for dog in self.__dogs:
            if dog.devState in self.__states:
                candidates.append(dog)
        self.debug_stream("Dealer candidates: %s" % (candidates))
        return candidates

    def distribute(self):
        raise NotImplementedError("No super class implementation")
    
    def doWrite(self, dog, attrName, value):
        try:
            dog.setExtraAttr(attrName, value)
        except Exception as e:
            self.error_stream(e)


class Equidistant(Dealer):
    def __init__(self, distance, *args, **kwargs):
        super(Equidistant, self).__init__(*args, **kwargs)
#         self.__distance = None
        self.distance = distance

    @property
    def distance(self):
        return self.__distance

    @distance.setter
    def distance(self, value):
        if type(value) in [int, long]:
            self.__distance = value
        else:
            raise TypeError("Must be an integer")

    def distribute(self):
        candidates = self.candidates
        distribution = range(0, len(candidates)*self.distance, self.distance)
        self.debug_stream("Dealer distribution: %s" % (distribution))
        for i, dog in enumerate(candidates):
            self.debug_stream("Working for candidate %d: %s"
                              % (i, dog.devName))
            for first, second in self.pairOfAttrs():
                self.doWrite(dog, first, distribution[i])
                self.doWrite(dog, second, distribution[-i])


class MinMax(Dealer):
    def __init__(self, max, min=0, *args, **kwargs):
        super(MinMax, self).__init__(*args, **kwargs)
#         self.__min = None
#         self.__max = None
        self.min = min
        self.max = max

    @property
    def min(self):
        return self.__min

    @min.setter
    def min(self, value):
        if type(value) is int:
            self.__min = value
        else:
            raise TypeError("Must be an integer")

    @property
    def max(self):
        return self.__max

    @max.setter
    def max(self, value):
        if type(value) is int:
            self.__max = value
        else:
            raise TypeError("Must be an integer")

    def distribute(self):
        candidates = self.candidates
        distribution = linspace(self.min, self.max, len(candidates))
        self.debug_stream("Dealer distribution: %s" % (distribution))
        for i, dog in enumerate(candidates):
            self.debug_stream("Working for candidate %d: %s"
                              % (i, dog.devName))
            for first, second in self.pairOfAttrs():
                self.doWrite(dog, first, int(distribution[i]))
                self.doWrite(dog, second, int(distribution[-i]))
