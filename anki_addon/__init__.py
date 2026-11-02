"""Crash-isolated AnkiCompanion entrypoint.

No network, database access, imports of the companion implementation, or
Qt objects run during Anki's add-on discovery. An integration failure must
NEVER stop the user's ordinary Anki launcher or other add-ons.
"""

_instance = None

def _start(*_args):
    global _instance
    try:
        from . import bridge
        bridge.opened()
        _instance = bridge
    except BaseException as error:
        # Anki must remain usable even if the entire integration fails to load.
        # Do not include tokens or user data in diagnostics.
        print('AnkiCompanion disabled after startup error:', type(error).__name__)
        _instance = None

def _stop(*_args):
    global _instance
    try:
        if _instance is not None:
            _instance.closed()
    except BaseException as error:
        print('AnkiCompanion shutdown error:', type(error).__name__)
    finally:
        _instance = None

def _answer(*args):
    try:
        if _instance is not None:
            _instance.answered(*args)
    except BaseException as error:
        print('AnkiCompanion answer hook disabled:', type(error).__name__)

def _sync(*args):
    try:
        if _instance is not None:
            _instance.synced(*args)
    except BaseException as error:
        print('AnkiCompanion sync hook disabled:', type(error).__name__)

try:
    from aqt import gui_hooks
    for _hook, _fn in (
        ('profile_did_open', _start),
        ('profile_will_close', _stop),
        ('reviewer_did_answer_card', _answer),
        ('sync_did_finish', _sync),
    ):
        _target = getattr(gui_hooks, _hook, None)
        if _target is not None:
            _target.append(_fn)
except BaseException as error:
    # Anki's add-on loader must not see exceptions from this optional package.
    print('AnkiCompanion startup isolation:', type(error).__name__)
