''' this contains the implementation for the WinDbg Debugger '''

import os
import re
import subprocess
import sys
import tempfile
import time

from csmlog_setup import getLogger
from debugger import Debugger
from frame import Frame
from stack import Stack
from variable import Variable
from windows_symbol_store import WindowsSymbolStore

MAX_STACK_DEPTH = 100
REGEX_FILE_AND_LINE_FROM_FRAME = re.compile(r'\[(.*)@\s*(\d+)')
DOWNSTREAM_TEMP_SYMBOLS = os.path.join(tempfile.gettempdir(), "DownstreamSymbols")

# think py2 would need this
if not hasattr(subprocess, 'DEVNULL'):
    subprocess.DEVNULL = open(os.devnull)

logger = getLogger(__file__)

class WinDbg(Debugger):
    CDB_DBG_PATH = r'C:\Program Files (x86)\Windows Kits\10\Debuggers\x86\cdb.exe'
    def _platformSetup(self):
        if not os.path.isfile(self.CDB_DBG_PATH):
            raise EnvironmentError("Could not find CDB: %s" % self.CDB_DBG_PATH)

        self._addSymbolsToDownstreamStoreIfNeeded()

        # add Microsoft symbol store
        # should we have a place to cache symbols other than self.symbols?
        self.symbols = "SRV*" + DOWNSTREAM_TEMP_SYMBOLS + "*" + self.symbols + "*http://msdl.microsoft.com/download/symbols"

    def _addSymbolsToDownstreamStoreIfNeeded(self):
        symStore = WindowsSymbolStore(DOWNSTREAM_TEMP_SYMBOLS)

        # if this is a file... add to store. As it will be downstream, it can't be compressed
        if os.path.isfile(self.symbols):
            symStore.add(self.symbols, compressed=False)

    def _startWinDbg(self):
        windbgRealPath = os.path.join(os.path.dirname(self.CDB_DBG_PATH), 'windbg.exe')
        return self._callWinDbg(debugCommandsList=[], exitAfterCommands=False, exeOverload=windbgRealPath, timeout=100000000000)

    def _callWinDbg(self, debugCommandsList, gotoExceptionContext=True, printHeaderFooter=True, exitAfterCommands=True, getJustCommandOutput=True, exeOverload=None, timeout=60):
        if isinstance(debugCommandsList, str):
            debugCommandsList = [debugCommandsList]

        if exitAfterCommands:
            debugCommandsList.append('q')

        if gotoExceptionContext:
            debugCommandsList = ['.ecxr'] + debugCommandsList

        # enable line numbers (since we need to do this to enable them for cdb. windbg has this enabled automatically)
        # see https://social.msdn.microsoft.com/Forums/en-US/a72dbabf-f8e2-4937-821e-a7ed37d41797/why-is-windbg-and-cdb-show-different-output-when-looking-at-the-stack-for-a-dump-file?forum=vsdebug
        debugCommandsList = ['.symopt+0x10'] + debugCommandsList

        outputHeader = None
        outputFooter = None
        if printHeaderFooter:
            finalCommandList = []
            for dc in debugCommandsList:
                finalCommandList.append('.echo == Start Calling %s ==' % dc)

                # only set header once
                if outputHeader is None:

                    # if this was auto added, don't consider it part of this.
                    if (not (gotoExceptionContext and dc == '.ecxr')) and dc != '.symopt+0x10':
                        outputHeader = finalCommandList[-1].split('.echo ', 1)[1]

                finalCommandList.append(dc)

                # Don't add a command after quit.
                if dc != 'q':
                    finalCommandList.append('.echo == End Calling %s ==' % dc)

                    # always overwrite footer
                    outputFooter = finalCommandList[-1].split('.echo ', 1)[1]

            debugCommandsList = finalCommandList

        # cheap... this will get deleted immediately but we'll have the path
        with tempfile.NamedTemporaryFile() as tempFile:
            tempFileName = tempFile.name

        if exeOverload is not None:
            exe = exeOverload
        else:
            exe = self.CDB_DBG_PATH

        cmdsWithSemiColons = ';'.join(debugCommandsList)
        args = [exe,
                "-z",
                self.crashDump,
                "-y",
                self.symbols,
                "-logo",
                tempFileName,
                "-c",
                cmdsWithSemiColons]

        if self.executable:
            args.extend(["-i", self.executable])
        try:
            logger.debug("About to call: %s" % args)
            process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            deathTime = time.time() + timeout
            process.poll()
            while deathTime > time.time():
                if process.returncode is None:
                    time.sleep(.01)
                    process.poll()
                else:
                    break
            else:
                process.terminate()
                raise RuntimeError("Timed out doing this command list: %s" % debugCommandsList)

            fullOutput = ''
            if os.path.exists(tempFile.name):
                with open(tempFile.name, 'r') as f:
                    fullOutput = f.read()

            if process.returncode != 0:
                logger.error("cdb error!\n%s" % fullOutput)
                raise subprocess.CalledProcessError(process.returncode, args)

            logger.debug("Output:\n%s" % fullOutput)

        finally:
            if os.path.isfile(tempFileName):
                try:
                    os.remove(tempFileName)
                except OSError:
                    pass

        # used to get rid of output we don't need
        if getJustCommandOutput and outputHeader and outputFooter:
            fullOutput = fullOutput.split(cmdsWithSemiColons, 1)[1]
            newOutput = fullOutput.split(outputHeader, 1)[1]
            fullOutput = newOutput.split(outputFooter, 1)[0]

            fullOutput = outputHeader + '\n' + fullOutput + '\n' + outputFooter

        return fullOutput

    def _callCommandOnEveryStackFrame(self, cmd):
        return self._callWinDbg(['!for_each_frame %s' % cmd])

    def _getRawStackTraceForEachFrame(self, formatCode='p'):
        return self._callCommandOnEveryStackFrame('k' + formatCode)

    def _getLineAndWarningForStackTrace(self, index, trace):
        warning = False
        for line in trace.splitlines():
            if not line.strip():
                continue

            if 'Stack unwind information not available' in line:
                warning = True
                continue

            firstThing = line.split()[0]
            try:
                int(firstThing)
            except ValueError:
                continue

            if int(firstThing) == index:
                return line.strip(), warning

    def _getVariablesForFrame(self, index):
        rawOutput = self._callWinDbg([
            '.frame %d' % index,
            'dv /t *',
        ])

        r"""example output
        == Start Calling .frame 0 ==

        00 010ffc14 00889ad9 TheCrasher!main+0x1b [c:\users\cmachalo\documents\visual studio 2015\projects\thecrasher\thecrasher\source.cpp @ 43]
        == End Calling .frame 0 ==
        == Start Calling dv /t * ==
        int argc = 0n1
        char ** argv = 0x032053f0
        char * p = 0x00000000 ""

        == End Calling dv /t * ==
        """

        variables = []
        for line in rawOutput.splitlines():
            if ' = ' in line:
                leftAndRight = line.split(' = ', 1)
                left, right = leftAndRight

                leftSplit = left.split()
                name = leftSplit[-1]
                typ = ' '.join(leftSplit[:-1])

                value = right

                # 0n syntax is weird. Get rid of it
                if value.startswith('0n'):
                    value = int(value.replace('0n', ''))

                v = Variable(typ, name, value)
                variables.append(v)

        return variables

    def _getThreadId(self):
        rawOutput = self._callWinDbg([
            '~.',
        ])
        r"""example output
        == Start Calling ~. ==

        .  0  Id: 97cc.e00 Suspend: 0 Teb: 00f81000 Unfrozen
            Priority: 0  Priority class: 32

        == End Calling ~. ==
        """
        for line in rawOutput.splitlines():
            if 'Id' in line:
                return int(line.split('Id', 1)[1].split('.', 1)[1].split()[0], 16)

    def getStackTrace(self):
        rawOutputClean = self._callWinDbg('kcn')
        rawOutputExtended = self._callWinDbg('kpn')

        frames = []

        for idx in range(MAX_STACK_DEPTH):
            x = self._getLineAndWarningForStackTrace(idx, rawOutputClean)
            if not x:
                break

            stackLine, warning = x
            moduleAndFunction = stackLine.split()[1]
            if '!' in moduleAndFunction:
                module, function = moduleAndFunction.split('!')
            else:
                module = moduleAndFunction
                function = None

            x = self._getLineAndWarningForStackTrace(idx, rawOutputExtended)
            extendedStackLine, warning = x
            match = re.findall(REGEX_FILE_AND_LINE_FROM_FRAME, extendedStackLine)
            if match:
                sourceFile, line = match[0]
            else:
                sourceFile = None
                line = None

            variables = self._getVariablesForFrame(idx)

            f = Frame(module, idx, function, sourceFile, line, variables=variables, warningAboutCorrectness=warning)

            frames.append(f)

        threadId = self._getThreadId()
        return Stack(frames, threadId)

    def getRawAnalysis(self):
        return self._callWinDbg([
            '!analyze -v',
            '.lastevent',
        ])

if __name__ == '__main__':
    w = WinDbg(r"C:\Users\csm10495\Desktop\TheCrasher\TestAll\6e71a81b-9d54-4966-be65-bbe7ef2b390a.dmp",
               r"C:\Users\csm10495\Desktop\TheCrasher\TestAll\TheCrasher.pdb",
               r"C:\Users\csm10495\Desktop\TheCrasher\TestAll\TheCrasher.exe")
