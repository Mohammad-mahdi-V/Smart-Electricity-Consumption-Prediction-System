"""control_panel/workers/signals.py

Why this file exists (read this before writing any page that runs a
long operation):

Five modules in services/ already do the right thing at the process
level -- they start their own background `threading.Thread`, and (for
model_service, initial_setup_service, script_service) the actual heavy
lifting runs in a completely separate OS *subprocess*, so a training
crash or a hung script can never take the GUI down with it:

    model_service.run_build(request, on_line, on_done)
    initial_setup_service.run_initial_setup(on_line, on_done)
    script_service.run_script(name, values, on_line, on_done)
    prediction_service.predict_async(device_id, on_done)
    prediction_service.force_predict_async(device_id, on_done)

The problem those functions have on the Qt side is the same problem
they had under Tkinter: `on_line`/`on_done` are called *from the
background thread*, and touching a widget from any thread other than
the GUI thread is unsafe. The Tkinter pages handled this with
`widget.after(0, ...)`. Qt's equivalent is a queued signal/slot
connection -- and the nice part is Qt does the thread-hop for you
automatically, based on which thread the *receiving* object lives on,
regardless of which thread called `.emit()`.

CallbackBridge below is the only piece needed to take advantage of
that. It's a QObject that is also directly callable, so you can hand
it to any of the `on_line`/`on_done`/... parameters
above exactly where a plain function was expected -- nothing in
services/ needs to change.

Usage in a page (created on the GUI thread, e.g. in on_navigate or a
button handler):

    from ..workers.signals import CallbackBridge

    self._on_line = CallbackBridge(self)
    self._on_line.fired.connect(lambda args: self.terminal.append_line(args[0]))

    self._on_done = CallbackBridge(self)
    self._on_done.fired.connect(lambda args: self._handle_build_done(*args))

    self._handle = model_service.run_build(request, on_line=self._on_line, on_done=self._on_done)

Keep a reference to each CallbackBridge (e.g. as `self._on_line`) for
as long as the operation can still call it -- like any QObject, it can
be garbage-collected if nothing holds onto it.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class CallbackBridge(QObject):
    """Callable adapter: calling it (from any thread) emits `fired`
    with all positional arguments packed into a tuple. Connect `fired`
    to a slot on the GUI thread before the background operation starts.
    """

    fired = Signal(tuple)

    def __call__(self, *args) -> None:
        self.fired.emit(args)