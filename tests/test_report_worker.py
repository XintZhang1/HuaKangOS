from dataclasses import replace
from unittest.mock import Mock
import threading

import pytest
from app import report_worker, scheduler


def test_web_does_not_start_scheduler_in_worker_mode(monkeypatch):
    monkeypatch.setattr(scheduler, 'settings', replace(scheduler.settings, scheduler_enabled=True, scheduler_mode='worker'))
    instance = scheduler.ReportScheduler()
    instance.start()
    assert instance.thread is None


def test_standalone_once_invokes_existing_idempotent_tick(monkeypatch):
    monkeypatch.setattr(report_worker, 'settings', replace(report_worker.settings, scheduler_enabled=True, scheduler_mode='worker'))
    tick = Mock()
    monkeypatch.setattr(report_worker, 'tick', tick)
    report_worker.run(once=True)
    tick.assert_called_once_with()


@pytest.mark.parametrize('enabled,mode', [(False, 'worker'), (True, 'embedded'), (True, 'off')])
def test_worker_refuses_ambiguous_or_disabled_configuration(monkeypatch, enabled, mode):
    monkeypatch.setattr(report_worker, 'settings', replace(report_worker.settings, scheduler_enabled=enabled, scheduler_mode=mode))
    tick = Mock()
    monkeypatch.setattr(report_worker, 'tick', tick)
    with pytest.raises(SystemExit):
        report_worker.run(once=True)
    tick.assert_not_called()


def test_worker_respects_shutdown_before_start(monkeypatch):
    monkeypatch.setattr(report_worker, 'settings', replace(report_worker.settings, scheduler_enabled=True, scheduler_mode='worker'))
    tick = Mock()
    monkeypatch.setattr(report_worker, 'tick', tick)
    event = threading.Event()
    event.set()
    report_worker.run(stop_event=event)
    tick.assert_not_called()
