"""Delivery of already claimed alerts; no decision authority or persistent state."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import math
import subprocess
import sys
from typing import Protocol

from decision.models.opportunity_alert import OpportunityAlert
from decision.runners.opportunity_alert_runner import OpportunityAlertCycleStatus


@dataclass(frozen=True, slots=True)
class NotificationPayload:
    project_key: str
    site_name: str
    window_start: datetime
    window_end: datetime
    expected_gain: float

    def __post_init__(self):
        for value in (self.project_key, self.site_name):
            if not isinstance(value, str) or not value.strip():
                raise ValueError('invalid_notification_text')
        for value in (self.window_start, self.window_end):
            if not isinstance(value, datetime) or value.utcoffset() is None:
                raise ValueError('invalid_notification_time')
        if self.window_end <= self.window_start:
            raise ValueError('invalid_notification_window')
        if (type(self.expected_gain) not in (int, float)
                or not math.isfinite(self.expected_gain) or self.expected_gain < 0):
            raise ValueError('invalid_notification_gain')

    @classmethod
    def from_alert(cls, alert: OpportunityAlert):
        return cls(alert.project_key, alert.site_name, alert.window_start,
            alert.window_end, alert.expected_gain)


class DeliveryStatus(str, Enum):
    DELIVERED = 'DELIVERED'
    FAILED = 'FAILED'
    SKIPPED = 'SKIPPED'


_REASONS = {
    DeliveryStatus.DELIVERED: {'accepted_by_os'},
    DeliveryStatus.FAILED: {'invalid_payload', 'delivery_timeout', 'process_failed', 'notifier_failed'},
    DeliveryStatus.SKIPPED: {'disabled', 'unsupported_platform'},
}


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    status: DeliveryStatus
    reason: str

    def __post_init__(self):
        if not isinstance(self.status, DeliveryStatus) or self.reason not in _REASONS[self.status]:
            raise ValueError('invalid_delivery_result')


class OpportunityAlertNotifier(Protocol):
    def notify(self, payload: NotificationPayload) -> DeliveryResult: ...


class DisabledNotifier:
    def notify(self, payload: NotificationPayload) -> DeliveryResult:
        return DeliveryResult(DeliveryStatus.SKIPPED, 'disabled')


def _display_text(value):
    # Bound presentation only. Data never becomes AppleScript source.
    return ''.join(' ' if ord(c) < 32 or 127 <= ord(c) < 160 else c for c in value)[:160]


def notification_text(payload):
    start = payload.window_start.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M')
    end = payload.window_end.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M')
    return (f'AstroPilot — {_display_text(payload.project_key)}',
        f'{_display_text(payload.site_name)} · {start} – {end} UTC · Gain attendu : {payload.expected_gain:.2f}')


_SCRIPT = '''on run argv
    display notification (item 2 of argv) with title (item 1 of argv)
end run
'''


class MacOSNotifier:
    def __init__(self, *, platform=None, process=None):
        self.platform = sys.platform if platform is None else platform
        self.process = subprocess.run if process is None else process

    def notify(self, payload: NotificationPayload) -> DeliveryResult:
        if self.platform != 'darwin':
            return DeliveryResult(DeliveryStatus.SKIPPED, 'unsupported_platform')
        if not isinstance(payload, NotificationPayload):
            return DeliveryResult(DeliveryStatus.FAILED, 'invalid_payload')
        try:
            title, message = notification_text(payload)
            result = self.process(['/usr/bin/osascript', '-', title, message],
                input=_SCRIPT, encoding='utf-8', shell=False, timeout=5,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if result.returncode == 0:
                return DeliveryResult(DeliveryStatus.DELIVERED, 'accepted_by_os')
        except subprocess.TimeoutExpired:
            return DeliveryResult(DeliveryStatus.FAILED, 'delivery_timeout')
        except (OSError, ValueError, UnicodeError):
            pass
        return DeliveryResult(DeliveryStatus.FAILED, 'process_failed')


def deliver_cycle(cycle, notifier: OpportunityAlertNotifier):
    """One attempt for an emitted cycle; failures never escape into decision state."""
    if cycle is None or cycle.status is not OpportunityAlertCycleStatus.ALERT_EMITTED:
        return None
    try:
        payload = NotificationPayload.from_alert(cycle.alert)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return DeliveryResult(DeliveryStatus.FAILED, 'invalid_payload')
    try:
        result = notifier.notify(payload)
        if isinstance(result, DeliveryResult):
            return result
    except Exception:
        pass
    return DeliveryResult(DeliveryStatus.FAILED, 'notifier_failed')
