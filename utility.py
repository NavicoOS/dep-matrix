#!/usr/bin/python2

# ################################################################################################ #
# Utility Functions for Scripting                                                                  #
# Author: Lazar Sumar                                                                              #
# Date:   23/01/2015                                                                               #
# ################################################################################################ #

import sys
import time

class Logger(object):
    def __init__(self):
        self.referenceTime = None
        self.isDbgEnabled = False
        self.isInfoEnabled = True
        self.isErrEnabled = True
    
    def _FormatMessage(self, messages):
        if self.referenceTime is not None:
            outMessage = '# {0: >6.2f}s: '.format(time.clock() - self.referenceTime)
        else:
            outMessage = ''
        
        outMessage += ' '.join([str(x) for x in messages])
        
        return outMessage
    
    def info(self, *message):
        if self.isInfoEnabled:
            print(self._FormatMessage(message))

    def dbg(self, *message):
        if self.isDbgEnabled:
            print(self._FormatMessage(message))
    
    def error(self, *message):
        if self.isErrEnabled:
            sys.stderr.write(self._FormatMessage(message))
            sys.stderr.write("\n")

def toPosixPath(path):
    return path.replace('\\', '/')