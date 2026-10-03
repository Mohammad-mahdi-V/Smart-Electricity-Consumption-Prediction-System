"""control_panel/workers/worker.py

A generic QThread wrapper for running one plain Python callable off the
GUI thread and getting its return value (or exception) back via
signals.

This is *not* what you want for model_service / initial_setup_service /
script_service / prediction_service -- those already run
their work in a background thread (and mostly a separate subprocess)
and just need `workers.signals.CallbackBridge` to deliver their
callbacks safely; wrapping them in a Worker on top would be a redundant
second layer of threading.

Reach for Worker when a page needs to call something else that's
synchronous and potentially slow -- for example a page-level helper
that isn't already one of the async service functions -- without
freezing the GUI while it runs.

Usage:

    self._worker = Worker(some_slow_function, arg1, arg2, keyword=value)
    self._worker.result.connect(self._on_result)
    self._worker.error.connect(self._on_error)
    self._worker.start()

Keep a reference to the Worker (e.g. `self._worker`) for as long as it
might still be running -- Qt can garbage-collect it otherwise, the same
gotcha as CallbackBridge.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    result = Signal(object)  # emitted with the callable's return value
    error = Signal(str)      # emitted with str(exception) if it raised, instead of result

    def __init__(self, fn: Callable[..., Any], *args, parent=None, **kwargs):
        super().__init__(parent)
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            value = self._fn(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001 - surface it to the GUI rather than dying silently
            self.error.emit(str(exc))
            return
        self.result.emit(value)