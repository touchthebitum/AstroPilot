"""Windows delivery adapter; consumes only the existing public notification payload."""
from __future__ import annotations

import base64
import json
import ntpath
import os
import subprocess
import sys

from astropilot.opportunity_alert_notification import (
    NotificationPayload, DeliveryResult, DeliveryStatus, notification_text,
)


# Fixed source only. Public text is decoded from stdin, never evaluated as code.
_WINDOWS_SCRIPT = r'''$ErrorActionPreference = 'Stop'
$window = $null
$added = $false
$exitCode = 1
try {
    $text = ConvertFrom-Json -InputObject ([Console]::In.ReadToEnd())
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class OpportunityBalloon {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct Data {
        public uint cbSize;
        public IntPtr hWnd;
        public uint uID, uFlags, uCallbackMessage;
        public IntPtr hIcon;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string szTip;
        public uint dwState, dwStateMask;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string szInfo;
        public uint uTimeout;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string szInfoTitle;
        public uint dwInfoFlags;
        public Guid guidItem;
        public IntPtr hBalloonIcon;
    }
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool Shell_NotifyIconW(uint operation, ref Data data);
}
'@
    if (-not [Environment]::UserInteractive) { throw 'interactive_desktop_required' }
    $window = New-Object System.Windows.Forms.Form
    $data = New-Object OpportunityBalloon+Data
    $data.cbSize = [Runtime.InteropServices.Marshal]::SizeOf($data)
    $data.hWnd = $window.Handle
    $data.uID = 1
    $data.uFlags = 2 # NIF_ICON
    $data.hIcon = [Drawing.SystemIcons]::Information.Handle
    $data.szTip = 'AstroPilot'
    $data.szInfo = ''
    $data.szInfoTitle = ''
    if (-not [OpportunityBalloon]::Shell_NotifyIconW(0, [ref]$data)) { throw 'icon_rejected' }
    $added = $true
    $data.uFlags = 16 # NIF_INFO
    $data.szInfoTitle = [string]$text[0]
    $data.szInfo = [string]$text[1]
    $data.dwInfoFlags = 1 # NIIF_INFO
    if (-not [OpportunityBalloon]::Shell_NotifyIconW(1, [ref]$data)) { throw 'notification_rejected' }
    # Keep the owner alive for a bounded interval; no click handlers or activation.
    $lifetime = [Diagnostics.Stopwatch]::StartNew()
    while ($lifetime.ElapsedMilliseconds -lt 10000) {
        [Windows.Forms.Application]::DoEvents()
        [Threading.Thread]::Sleep(50)
    }
    $exitCode = 0
} catch {
    $exitCode = 1
} finally {
    if ($added) { [void][OpportunityBalloon]::Shell_NotifyIconW(2, [ref]$data) }
    if ($null -ne $window) { $window.Dispose() }
}
exit $exitCode
'''
_ENCODED_SCRIPT = base64.b64encode(_WINDOWS_SCRIPT.encode('utf-16-le')).decode('ascii')


def _native_text(value, units):
    # Native WCHAR capacities include their terminating NUL. Preserve whole pairs.
    return value.encode('utf-16-le')[:units * 2].decode('utf-16-le', errors='ignore')


class WindowsNotifier:
    def __init__(self, *, platform=None, process=None, system_root=None):
        self.platform = sys.platform if platform is None else platform
        self.process = subprocess.run if process is None else process
        self.system_root = os.environ.get('SystemRoot', '') if system_root is None else system_root

    def notify(self, payload: NotificationPayload) -> DeliveryResult:
        if not isinstance(payload, NotificationPayload):
            return DeliveryResult(DeliveryStatus.FAILED, 'invalid_payload')
        # Explicitly requested but unavailable Windows delivery fails, never falls back.
        if self.platform != 'win32':
            return DeliveryResult(DeliveryStatus.FAILED, 'process_failed')
        try:
            root = self.system_root
            if (not isinstance(root, str) or not ntpath.isabs(root)
                    or not ntpath.splitdrive(root)[0].endswith(':')):
                return DeliveryResult(DeliveryStatus.FAILED, 'process_failed')
            executable = ntpath.join(root, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
            title, message = notification_text(payload)
            data = json.dumps([_native_text(title, 63), _native_text(message, 255)], ensure_ascii=True)
            result = self.process([executable, '-NoProfile', '-NonInteractive', '-Sta',
                '-WindowStyle', 'Hidden', '-EncodedCommand', _ENCODED_SCRIPT],
                input=data, encoding='ascii', shell=False, timeout=20,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if result.returncode == 0:
                return DeliveryResult(DeliveryStatus.DELIVERED, 'accepted_by_os')
        except subprocess.TimeoutExpired:
            return DeliveryResult(DeliveryStatus.FAILED, 'delivery_timeout')
        except (OSError, ValueError, UnicodeError):
            pass
        return DeliveryResult(DeliveryStatus.FAILED, 'process_failed')
