"""Presentation of evaluated Guardian results; no evaluation or action authority."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
import sys
from decision.models.guardian import (
    GuardianRiskLevel, GuardianAction, GuardianSessionState, GuardianActionApplicability,
)
from decision.models.guardian_cycle import GuardianCycleResult, GuardianCycleStatus
from astropilot.local_notification import DeliveryStatus, DeliveryResult, MacOSChannel, WindowsChannel

VERSION = 'guardian-notification-v1'
REASONS = frozenset(
    f'{channel}:{reason}'
    for channel in ('rain_active','rain_eta_minutes','wind_kmh','gust_kmh','humidity_percent','dew_spread_c')
    for reason in ('WATCH','WARNING','CRITICAL','missing_invalid_untrusted_or_stale')
)

@dataclass(frozen=True, slots=True)
class GuardianNotificationPolicy:
    enabled: bool = False
    min_level: GuardianRiskLevel = GuardianRiskLevel.WARNING
    version: str = VERSION

    def __post_init__(self):
        if (type(self.enabled) is not bool or not isinstance(self.min_level, GuardianRiskLevel)
                or self.version != VERSION):
            raise ValueError('invalid_notification_policy')

    @classmethod
    def from_config(cls, doc):
        if not isinstance(doc, dict) or not set(doc) <= {'version','enabled','min_level'}:
            raise ValueError('invalid_notification_policy')
        try:
            return cls(doc.get('enabled', False), GuardianRiskLevel[doc.get('min_level','WARNING')],
                       doc.get('version', VERSION))
        except (KeyError, TypeError):
            raise ValueError('invalid_notification_policy') from None

@dataclass(frozen=True, slots=True)
class NotificationPayload:
    risk_level: GuardianRiskLevel
    recommended_action: GuardianAction
    session_state: GuardianSessionState
    action_applicability: GuardianActionApplicability
    reasons: tuple[str, ...]
    assessed_at: datetime
    logical_time: datetime

    def __post_init__(self):
        for value, kind in ((self.risk_level,GuardianRiskLevel),(self.recommended_action,GuardianAction),
                            (self.session_state,GuardianSessionState),(self.action_applicability,GuardianActionApplicability)):
            if not isinstance(value,kind): raise ValueError('invalid_payload')
        if not isinstance(self.reasons,tuple) or any(r not in REASONS for r in self.reasons):
            raise ValueError('invalid_payload')
        for value in (self.assessed_at,self.logical_time):
            if not isinstance(value,datetime) or value.utcoffset() is None: raise ValueError('invalid_payload')

    @classmethod
    def from_cycle(cls, cycle):
        if not isinstance(cycle,GuardianCycleResult) or cycle.status is not GuardianCycleStatus.ASSESSED:
            raise ValueError('invalid_payload')
        a = cycle.assessment
        return cls(a.risk_level,cycle.recommended_action,a.session_state,a.action_applicability,
                   tuple(dict.fromkeys(r for r in a.reasons if r in REASONS)),a.assessed_at,cycle.logical_time)

class NotificationChannel(Protocol):
    def deliver(self, title: str, message: str) -> DeliveryResult: ...


def notification_text(payload):
    uncertainty = 'Evidence uncertain. ' if payload.risk_level is GuardianRiskLevel.UNKNOWN else ''
    time = payload.logical_time.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    return (f'Guardian — {payload.risk_level.name}',
        f'{uncertainty}Recommendation: {payload.recommended_action.name}. No action executed. '
        f'Session: {payload.session_state.name}; applicability: {payload.action_applicability.name}. {time}')

class GuardianNotifier:
    def __init__(self, channel: NotificationChannel, policy=GuardianNotificationPolicy()):
        if not isinstance(policy,GuardianNotificationPolicy): raise ValueError('invalid_notification_policy')
        self.channel = channel
        self.policy = policy

    def notify(self, payload: NotificationPayload) -> DeliveryResult:
        if not self.policy.enabled: return DeliveryResult(DeliveryStatus.SKIPPED,'disabled')
        if not isinstance(payload,NotificationPayload): return DeliveryResult(DeliveryStatus.FAILED,'invalid_payload')
        if payload.risk_level < self.policy.min_level: return DeliveryResult(DeliveryStatus.SKIPPED,'below_min_level')
        try:
            result = self.channel.deliver(*notification_text(payload))
            if isinstance(result,DeliveryResult): return result
        except Exception:
            pass
        return DeliveryResult(DeliveryStatus.FAILED,'notifier_failed')


def local_notifier(policy):
    channel = WindowsChannel() if sys.platform == 'win32' else MacOSChannel()
    return GuardianNotifier(channel,policy)


def deliver_cycle(cycle, notifier):
    if cycle is None or cycle.status is not GuardianCycleStatus.ASSESSED:
        return DeliveryResult(DeliveryStatus.SKIPPED,'not_assessed')
    try:
        payload = NotificationPayload.from_cycle(cycle)
    except (AttributeError,TypeError,ValueError,OverflowError):
        return DeliveryResult(DeliveryStatus.FAILED,'invalid_payload')
    try:
        result = notifier.notify(payload)
        if isinstance(result,DeliveryResult): return result
    except Exception:
        pass
    return DeliveryResult(DeliveryStatus.FAILED,'notifier_failed')
