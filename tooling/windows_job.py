"""Windows child containment: parent death closes the sole kill-on-close job."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import socket
import subprocess
import time


class _BasicLimits(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong),
                ('PerJobUserTimeLimit', ctypes.c_longlong),
                ('LimitFlags', wintypes.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.c_size_t),
                ('PriorityClass', wintypes.DWORD),
                ('SchedulingClass', wintypes.DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
                ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', _BasicLimits), ('IoInfo', _IoCounters),
                ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]


class WindowsJob:
    def __init__(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        for name, args, result in (
            ('CreateJobObjectW', [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            ('SetInformationJobObject', [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            ('AssignProcessToJobObject', [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            ('CloseHandle', [wintypes.HANDLE], wintypes.BOOL),
        ):
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = args, result
        # NULL security attributes: handle is not inherited by the child.
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, child):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(child._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class _StartupInfo(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('lpReserved', wintypes.LPWSTR),
                ('lpDesktop', wintypes.LPWSTR), ('lpTitle', wintypes.LPWSTR),
                *[(n, wintypes.DWORD) for n in ('dwX', 'dwY', 'dwXSize', 'dwYSize',
                    'dwXCountChars', 'dwYCountChars', 'dwFillAttribute', 'dwFlags')],
                ('wShowWindow', wintypes.WORD), ('cbReserved2', wintypes.WORD),
                ('lpReserved2', ctypes.c_void_p), ('hStdInput', wintypes.HANDLE),
                ('hStdOutput', wintypes.HANDLE), ('hStdError', wintypes.HANDLE)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [('hProcess', wintypes.HANDLE), ('hThread', wintypes.HANDLE),
                ('dwProcessId', wintypes.DWORD), ('dwThreadId', wintypes.DWORD)]


class _Accounting(ctypes.Structure):
    _fields_ = [(n, ctypes.c_longlong) for n in ('TotalUserTime', 'TotalKernelTime',
                'ThisPeriodTotalUserTime', 'ThisPeriodTotalKernelTime')] + [
                (n, wintypes.DWORD) for n in ('TotalPageFaultCount', 'TotalProcesses',
                'ActiveProcesses', 'TotalTerminatedProcesses')]


class _TcpRow(ctypes.Structure):
    _fields_ = [(n, wintypes.DWORD) for n in ('state', 'local_address', 'local_port',
                'remote_address', 'remote_port', 'pid')]


class IsolatedProcess:
    """Assign the suspended process before it can create a PyInstaller child."""

    def __init__(self, argv, cwd, env):
        self.job = WindowsJob()
        self.kernel = self.job.kernel
        self._handle = None
        self.stopped = False
        definitions = (
            ('CreateProcessW', [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p,
                ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p,
                wintypes.LPCWSTR, ctypes.POINTER(_StartupInfo),
                ctypes.POINTER(_ProcessInfo)], wintypes.BOOL),
            ('ResumeThread', [wintypes.HANDLE], wintypes.DWORD),
            ('GetExitCodeProcess', [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            ('WaitForSingleObject', [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            ('TerminateProcess', [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            ('TerminateJobObject', [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            ('QueryInformationJobObject', [wintypes.HANDLE, ctypes.c_int,
                ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
            ('OpenProcess', [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            ('IsProcessInJob', [wintypes.HANDLE, wintypes.HANDLE,
                ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL),
        )
        for name, args, result in definitions:
            fn = getattr(self.kernel, name)
            fn.argtypes, fn.restype = args, result
        si = _StartupInfo()
        si.cb = ctypes.sizeof(si)
        pi = _ProcessInfo()
        environment = ctypes.create_unicode_buffer('\0'.join(
            key + '=' + value for key, value in sorted(env.items(), key=lambda x: x[0].upper())) + '\0\0')
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
        try:
            # Suspended + Unicode environment + no console; no inherited handles.
            if not self.kernel.CreateProcessW(argv[0], command, None, None, False,
                    0x00000004 | 0x00000400 | 0x08000000, environment,
                    str(cwd), ctypes.byref(si), ctypes.byref(pi)):
                raise ctypes.WinError(ctypes.get_last_error())
            self._handle = pi.hProcess
            self.pid = pi.dwProcessId
            self.job.assign(self)
            if self.kernel.ResumeThread(pi.hThread) == 0xffffffff:
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            if self._handle:
                self.kernel.TerminateProcess(self._handle, 1)
                self.kernel.WaitForSingleObject(self._handle, 10000)
                self.kernel.CloseHandle(self._handle)
                self._handle = None
            self.job.close()
            raise
        finally:
            if pi.hThread:
                self.kernel.CloseHandle(pi.hThread)

    def poll(self):
        code = wintypes.DWORD()
        if not self.kernel.GetExitCodeProcess(self._handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return None if code.value == 259 else code.value

    def owns_pid(self, pid):
        handle = self.kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            result = wintypes.BOOL()
            if not self.kernel.IsProcessInJob(handle, self.job.handle, ctypes.byref(result)):
                raise ctypes.WinError(ctypes.get_last_error())
            return bool(result.value)
        finally:
            self.kernel.CloseHandle(handle)

    def listener_pid(self, port=8000):
        """Read native TCP ownership; never trust an unrelated local server."""
        api = ctypes.WinDLL('iphlpapi', use_last_error=True).GetExtendedTcpTable
        api.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
                       wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
        api.restype = wintypes.DWORD
        size = wintypes.DWORD()
        result = api(None, ctypes.byref(size), False, socket.AF_INET, 3, 0)
        if result != 122:
            raise OSError(result, 'GetExtendedTcpTable size')
        for _ in range(3):
            buf = ctypes.create_string_buffer(size.value)
            result = api(buf, ctypes.byref(size), False, socket.AF_INET, 3, 0)
            if result == 122:
                continue
            if result:
                raise OSError(result, 'GetExtendedTcpTable')
            count = wintypes.DWORD.from_buffer(buf).value
            rows = (_TcpRow * count).from_buffer(buf, ctypes.sizeof(wintypes.DWORD))
            pids = {row.pid for row in rows if row.state == 2
                    and socket.ntohs(row.local_port & 0xffff) == port}
            if not pids:
                return None
            if len(pids) != 1 or not all(self.owns_pid(pid) for pid in pids):
                raise RuntimeError('Le port appartient à un autre processus : aucun appel API autorisé.')
            return next(iter(pids))
        raise RuntimeError('Inventaire TCP instable.')

    def close(self):
        if not self._handle:
            return
        try:
            if not self.kernel.TerminateJobObject(self.job.handle, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            deadline = time.monotonic() + 20
            while True:
                info = _Accounting()
                if not self.kernel.QueryInformationJobObject(self.job.handle, 1,
                        ctypes.byref(info), ctypes.sizeof(info), None):
                    raise ctypes.WinError(ctypes.get_last_error())
                if info.ActiveProcesses == 0:
                    self.stopped = True
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('Des processus de test subsistent dans le Job Object.')
                time.sleep(.1)
        finally:
            self.job.close()  # Also kills all descendants if the check failed.
            self.kernel.CloseHandle(self._handle)
            self._handle = None
