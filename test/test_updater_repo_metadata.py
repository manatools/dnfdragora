#!/usr/bin/env python3
"""Unit tests for updater repo metadata download handling."""

import os
import sys
import types
import threading
from queue import Queue

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _install_qt_stubs():
    if 'PySide6' in sys.modules:
        return

    pyside6 = types.ModuleType('PySide6')
    qtwidgets = types.ModuleType('PySide6.QtWidgets')
    qtgui = types.ModuleType('PySide6.QtGui')
    qtcore = types.ModuleType('PySide6.QtCore')

    class QApplication:
        _instance = None

        def __init__(self, *_args, **_kwargs):
            QApplication._instance = self

        @staticmethod
        def instance():
            return QApplication._instance

        def setQuitOnLastWindowClosed(self, *_args, **_kwargs):
            return None

        def exec(self):
            return 0

        def quit(self):
            return None

    class QMenu:
        def addAction(self, *_args, **_kwargs):
            return None

        def addSeparator(self):
            return None

    class QSystemTrayIcon:
        class MessageIcon:
            Information = 0
            Warning = 1

        class ActivationReason:
            Trigger = 1

        def __init__(self, *_args, **_kwargs):
            self._visible = False

        @staticmethod
        def supportsMessages():
            return False

        @staticmethod
        def isSystemTrayAvailable():
            return True

        def setToolTip(self, *_args, **_kwargs):
            return None

        def setContextMenu(self, *_args, **_kwargs):
            return None

        def setIcon(self, *_args, **_kwargs):
            return None

        def isVisible(self):
            return self._visible

        def show(self):
            self._visible = True

        def hide(self):
            self._visible = False

        def showMessage(self, *_args, **_kwargs):
            return None

    class QMessageBox:
        class Icon:
            Critical = 0

        def setIcon(self, *_args, **_kwargs):
            return None

        def setText(self, *_args, **_kwargs):
            return None

        def setInformativeText(self, *_args, **_kwargs):
            return None

        def setWindowTitle(self, *_args, **_kwargs):
            return None

        def exec(self):
            return None

    class QIcon:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def fromTheme(_name):
            return QIcon()

        def isNull(self):
            return False

    class QTimer:
        def __init__(self):
            self.timeout = types.SimpleNamespace(connect=lambda *_args, **_kwargs: None)

        def setInterval(self, *_args, **_kwargs):
            return None

        def start(self):
            return None

        def stop(self):
            return None

        @staticmethod
        def singleShot(_msec, callback):
            callback()

    class QCoreApplication:
        @staticmethod
        def processEvents(*_args, **_kwargs):
            return None

    class _ProcessEventsFlag:
        AllEvents = 0

    class QEventLoop:
        ProcessEventsFlag = _ProcessEventsFlag

    qtwidgets.QApplication = QApplication
    qtwidgets.QMenu = QMenu
    qtwidgets.QSystemTrayIcon = QSystemTrayIcon
    qtwidgets.QMessageBox = QMessageBox
    qtgui.QIcon = QIcon
    qtcore.QCoreApplication = QCoreApplication
    qtcore.QEventLoop = QEventLoop
    qtcore.QTimer = QTimer

    sys.modules['PySide6'] = pyside6
    sys.modules['PySide6.QtWidgets'] = qtwidgets
    sys.modules['PySide6.QtGui'] = qtgui
    sys.modules['PySide6.QtCore'] = qtcore


def _install_dnfdragora_stubs():
    if 'dnfdragora.config' not in sys.modules:
        config_mod = types.ModuleType('dnfdragora.config')

        class AppConfig:
            def __init__(self, *_args, **_kwargs):
                self.userPreferences = None

        config_mod.AppConfig = AppConfig
        sys.modules['dnfdragora.config'] = config_mod

    if 'dnfdragora.misc' not in sys.modules:
        misc_mod = types.ModuleType('dnfdragora.misc')
        misc_mod.logger_setup = lambda *_args, **_kwargs: None
        sys.modules['dnfdragora.misc'] = misc_mod

    if 'dnfdragora.ui' not in sys.modules:
        ui_mod = types.ModuleType('dnfdragora.ui')
        ui_mod.mainGui = lambda *_args, **_kwargs: None
        sys.modules['dnfdragora.ui'] = ui_mod

    if 'dnfdragora.dnfd_client' not in sys.modules:
        dnfd_mod = types.ModuleType('dnfdragora.dnfd_client')

        class Client:
            def __init__(self):
                self.session_path = '/session/test'

        dnfd_mod.Client = Client
        sys.modules['dnfdragora.dnfd_client'] = dnfd_mod


_install_qt_stubs()
_install_dnfdragora_stubs()

from dnfdragora.updater import Updater
import dnfdragora.updater as updater_module


if not hasattr(sys.modules['dnfdragora.updater'], '_'):
    sys.modules['dnfdragora.updater']._ = lambda text: text


def _make_updater_stub():
    upd = object.__new__(Updater)
    upd._Updater__backend = types.SimpleNamespace(session_path='/session/test')
    upd._Updater__repo_md_active_ids = set()
    upd._Updater__repo_md_seen_ids = set()
    upd._Updater__repo_md_followup_scheduled = False
    upd._Updater__running = True
    upd._Updater__dialog_open = False
    scheduled = []
    upd._Updater__reschedule_update_in = (
        lambda minutes=0, seconds=0:
        scheduled.append({'minutes': minutes, 'seconds': seconds}) or True
    )
    return upd, scheduled


def test_repo_download_events_are_classified_and_rescheduled_on_end():
    upd, scheduled = _make_updater_stub()

    repo_info = {
        'session_object_path': '/session/test',
        'download_id': 'repo:updates',
        'description': 'Fedora Updates',
        'total_to_download': -1,
    }

    assert upd._Updater__handle_repo_metadata_download('OnDownloadStart', repo_info) is True
    assert 'repo:updates' in upd._Updater__repo_md_active_ids
    assert scheduled == []

    progress_info = dict(repo_info, downloaded=0)
    assert upd._Updater__handle_repo_metadata_download('OnDownloadProgress', progress_info) is True
    assert scheduled == []

    end_info = dict(repo_info, status=0, error='Successfully downloaded')
    assert upd._Updater__handle_repo_metadata_download('OnDownloadEnd', end_info) is True
    assert upd._Updater__repo_md_followup_scheduled is True
    assert scheduled == [{'minutes': 0, 'seconds': Updater.RESCHEDULE_INTERVAL_SEC}]


def test_package_download_events_are_not_treated_as_repo_metadata():
    upd, scheduled = _make_updater_stub()

    pkg_info = {
        'session_object_path': '/session/test',
        'download_id': 'package:12345',
        'description': 'bash',
        'total_to_download': 4096,
    }

    assert upd._Updater__handle_repo_metadata_download('OnDownloadStart', pkg_info) is False
    assert upd._Updater__repo_md_active_ids == set()
    assert scheduled == []


def test_check_updates_does_not_hide_tray_when_hide_menu_enabled():
    upd = object.__new__(Updater)
    upd._Updater__hide_menu = True
    upd._Updater__dialog_open = False
    upd._Updater__getUpdatesRequested = False

    tray_visibility_calls = []
    update_checks = []

    upd._Updater__set_tray_visible = (
        lambda visible, reason='': tray_visibility_calls.append((visible, reason))
    )
    upd._Updater__get_updates = lambda: update_checks.append('called')

    upd._Updater__check_updates()

    assert tray_visibility_calls == []
    assert update_checks == ['called']
    assert upd._Updater__getUpdatesRequested is True


def _make_check_result_updater(hide_menu):
    upd = object.__new__(Updater)
    upd._Updater__hide_menu = hide_menu
    upd._Updater__dnf_provider_enabled = True
    upd._Updater__getUpdatesRequested = False
    upd._Updater__has_updates = False
    upd._Updater__update_count = 0
    upd._Updater__plugin_updates = {}
    upd._Updater__plugin_updates_lock = threading.Lock()
    upd._Updater__update_provider_lock = threading.Lock()
    upd._Updater__update_provider_states = {
        Updater.DNF_PROVIDER_ID: updater_module.UpdateProviderState(
            provider_id=Updater.DNF_PROVIDER_ID,
            display_name='dnf',
            include_in_extra_menu=False,
            icon_name='dnfdragora',
            plugin=None
        )
    }
    upd._Updater__update_provider_counts = {
        Updater.DNF_PROVIDER_ID: 0
    }
    upd._Updater__check_gen = 1
    upd._tray_update_action = None
    return upd


def test_updates_found_keeps_tray_visible_and_notifies_when_hide_menu_false():
    upd = _make_check_result_updater(hide_menu=False)

    icon_calls = []
    visible_calls = []
    messages = []
    tooltips = []

    class TrayRecorder:
        def showMessage(self, *args):
            messages.append(args)

        def setToolTip(self, text):
            tooltips.append(text)

    upd._tray = TrayRecorder()
    upd._Updater__set_tray_icon = lambda name, reason='': icon_calls.append((name, reason))
    upd._Updater__set_tray_visible = lambda visible, reason='': visible_calls.append((visible, reason))

    original_supports_messages = updater_module.QSystemTrayIcon.supportsMessages
    updater_module.QSystemTrayIcon.supportsMessages = staticmethod(lambda: True)
    try:
        upd._Updater__handle_check_result(4, gen=1)
    finally:
        updater_module.QSystemTrayIcon.supportsMessages = original_supports_messages

    assert icon_calls[-1] == ('system-software-update', 'updates found')
    assert visible_calls[-1] == (True, 'updates found')
    assert len(messages) == 1
    assert messages[0][0] == 'dnfdragora-update'
    assert 'dnf (4)' in messages[0][1]
    assert tooltips[-1] == 'dnfdragora-updater - 4 updates available.'


def test_no_updates_hides_tray_when_hide_menu_true():
    upd = _make_check_result_updater(hide_menu=True)

    visible_calls = []
    tooltips = []

    class TrayRecorder:
        def showMessage(self, *args):
            return None

        def setToolTip(self, text):
            tooltips.append(text)

    upd._tray = TrayRecorder()
    upd._Updater__set_tray_icon = lambda *_args, **_kwargs: None
    upd._Updater__set_tray_visible = lambda visible, reason='': visible_calls.append((visible, reason))

    upd._Updater__handle_check_result(0, gen=1)

    assert visible_calls[-1] == (False, 'no updates, hide_menu')
    assert tooltips[-1] == 'dnfdragora-updater'


def test_no_updates_keeps_tray_visible_when_hide_menu_false():
    upd = _make_check_result_updater(hide_menu=False)

    visible_calls = []

    class TrayRecorder:
        def showMessage(self, *args):
            return None

        def setToolTip(self, _text):
            return None

    upd._tray = TrayRecorder()
    upd._Updater__set_tray_icon = lambda *_args, **_kwargs: None
    upd._Updater__set_tray_visible = lambda visible, reason='': visible_calls.append((visible, reason))

    upd._Updater__handle_check_result(0, gen=1)

    assert visible_calls[-1] == (True, 'no updates, always-visible')


def test_get_updates_refreshes_plugin_cache_in_background_phase():
    upd = object.__new__(Updater)
    upd._Updater__dialog_open = False
    upd._Updater__dnf_provider_enabled = True
    upd._Updater__check_gen = 0
    upd._Updater__plugin_updates_lock = threading.Lock()
    upd._Updater__update_provider_lock = threading.Lock()
    upd._Updater__plugin_updates = {}
    upd._Updater__update_provider_states = {}
    upd._Updater__update_provider_counts = {}
    upd._Updater__reset_repo_metadata_tracking = lambda: None

    call_order = []

    class Backend:
        def __init__(self):
            from queue import Queue
            self.session_path = '/session/test'
            self.eventQueue = Queue()

        def ResetSession(self, sync=True):
            call_order.append('reset_session')

        def GetPackages(self, _options, piped=False):
            call_order.append('get_packages')

        def reloadDaemon(self):
            call_order.append('reload_daemon')

    upd._Updater__backend = Backend()
    upd._Updater__refresh_update_providers = lambda _dnf=None: call_order.append('refresh_plugins')

    upd._Updater__get_updates()

    assert call_order == ['reset_session', 'get_packages']


def test_handle_check_result_uses_cached_plugin_updates_only():
    upd = _make_check_result_updater(hide_menu=False)
    cached_provider_id = "plugin::CachedPlugin"
    with upd._Updater__update_provider_lock:
        upd._Updater__update_provider_states[cached_provider_id] = (
            updater_module.UpdateProviderState(
                provider_id=cached_provider_id,
                display_name='CachedPlugin',
                include_in_extra_menu=True,
                icon_name=None,
                plugin=object()
            )
        )
        upd._Updater__update_provider_counts[cached_provider_id] = 2

    icon_calls = []
    visible_calls = []
    messages = []

    class TrayRecorder:
        def showMessage(self, *args):
            messages.append(args)

        def setToolTip(self, _text):
            return None

    upd._tray = TrayRecorder()
    upd._Updater__set_tray_icon = lambda name, reason='': icon_calls.append((name, reason))
    upd._Updater__set_tray_visible = lambda visible, reason='': visible_calls.append((visible, reason))

    original_supports_messages = updater_module.QSystemTrayIcon.supportsMessages
    updater_module.QSystemTrayIcon.supportsMessages = staticmethod(lambda: True)
    try:
        upd._Updater__handle_check_result(0, gen=1)
    finally:
        updater_module.QSystemTrayIcon.supportsMessages = original_supports_messages

    assert icon_calls[-1] == ('system-software-update', 'updates found')
    assert visible_calls[-1] == (True, 'updates found')
    assert len(messages) == 1
    assert 'CachedPlugin (2)' in messages[0][1]


def test_refresh_update_providers_registers_internal_and_external_paths():
    upd = object.__new__(Updater)
    upd._Updater__dnf_provider_enabled = True
    upd._Updater__plugin_loader = types.SimpleNamespace()
    upd._Updater__plugin_updates_lock = threading.Lock()
    upd._Updater__update_provider_lock = threading.Lock()
    upd._Updater__plugin_updates = {}
    upd._Updater__update_provider_states = {}
    upd._Updater__update_provider_counts = {}

    plugin = types.SimpleNamespace(name='ExternalPlugin', icon_name='external-icon')
    upd._Updater__plugin_loader.discover_plugins = lambda: None
    upd._Updater__plugin_loader.get_plugins_for_updater = lambda: [plugin]
    upd._Updater__plugin_loader.get_total_plugin_updates = lambda timeout_sec=5.0: {
        'ExternalPlugin': 3
    }

    upd._Updater__refresh_update_providers(dnf_count=5)
    total_count, dnf_count, plugin_counts = upd._Updater__get_total_update_count()
    provider_states, provider_counts = upd._Updater__get_update_providers_snapshot()

    assert total_count == 8
    assert dnf_count == 5
    assert plugin_counts == {'ExternalPlugin': 3}
    assert provider_counts[Updater.DNF_PROVIDER_ID] == 5
    assert provider_states[Updater.DNF_PROVIDER_ID].include_in_extra_menu is False


def test_provider_only_mode_works_without_dnf_provider():
    upd = object.__new__(Updater)
    upd._Updater__dialog_open = False
    upd._Updater__dnf_provider_enabled = False
    upd._Updater__check_gen = 0
    upd._Updater__backend = None
    upd._Updater__plugin_updates_lock = threading.Lock()
    upd._Updater__update_provider_lock = threading.Lock()
    upd._Updater__plugin_updates = {}
    upd._Updater__update_provider_states = {}
    upd._Updater__update_provider_counts = {}
    upd._Updater__repo_md_active_ids = set()
    upd._Updater__repo_md_seen_ids = set()
    upd._Updater__repo_md_followup_scheduled = False
    upd._Updater__reset_repo_metadata_tracking = lambda: None
    upd._gui_queue = Queue()

    plugin_provider_id = "plugin::OnlyPlugin"
    upd._Updater__refresh_update_providers = lambda dnf_count=None: (
        upd._Updater__update_provider_states.update({
            plugin_provider_id: updater_module.UpdateProviderState(
                provider_id=plugin_provider_id,
                display_name='OnlyPlugin',
                include_in_extra_menu=True,
                icon_name=None,
                plugin=object()
            )
        }),
        upd._Updater__update_provider_counts.update({plugin_provider_id: 4})
    )

    upd._Updater__get_updates()

    cmd, count, gen = upd._gui_queue.get_nowait()
    assert cmd == 'updates_found'
    assert count == 4
    assert gen == 1


def test_update_loop_does_not_access_backend_queue_when_provider_disabled():
    upd = object.__new__(Updater)
    upd._Updater__running = True
    upd._Updater__dialog_open = False
    upd._Updater__dnf_provider_enabled = False
    upd._Updater__backend = None
    upd._Updater__updateInterval = 1
    upd._Updater__get_updates = lambda *args, **kwargs: None

    class FakeScheduler:
        def __init__(self):
            self._empty = True
            self.enter_calls = 0

        def empty(self):
            return self._empty

        def enter(self, *_args, **_kwargs):
            self.enter_calls += 1
            self._empty = False

        def run(self, blocking=False):
            assert blocking is False
            upd._Updater__running = False

    upd._Updater__scheduler = FakeScheduler()

    original_sleep = updater_module.time.sleep
    updater_module.time.sleep = lambda _seconds: None
    try:
        upd._Updater__update_loop()
    finally:
        updater_module.time.sleep = original_sleep

    assert upd._Updater__scheduler.enter_calls == 1


def test_tray_left_click_does_not_open_update_when_dnf_provider_disabled():
    upd = object.__new__(Updater)
    upd._Updater__dnf_provider_enabled = False
    upd._Updater__has_updates = True
    upd._Updater__suppress_context_menu_once = False

    run_update_calls = []
    upd._Updater__run_update = lambda: run_update_calls.append('called')

    upd._Updater__on_tray_activated(
        updater_module.QSystemTrayIcon.ActivationReason.Trigger
    )

    assert run_update_calls == []
    assert upd._Updater__suppress_context_menu_once is False


def test_run_dialog_is_noop_when_dnf_provider_disabled():
    upd = object.__new__(Updater)
    upd._Updater__dnf_provider_enabled = False
    upd._Updater__dialog_open = False
    upd._Updater__main_gui = None
    upd._tray = types.SimpleNamespace(isVisible=lambda: True)

    upd._Updater__run_dialog({'update_only': True})

    assert upd._Updater__dialog_open is False
    assert upd._Updater__main_gui is None


def test_refresh_dnf_action_uses_parenthesized_count_and_icon():
    upd = object.__new__(Updater)
    upd._Updater__dnf_provider_enabled = True
    upd._Updater__update_provider_lock = threading.Lock()
    upd._Updater__update_provider_states = {
        Updater.DNF_PROVIDER_ID: updater_module.UpdateProviderState(
            provider_id=Updater.DNF_PROVIDER_ID,
            display_name='dnf',
            include_in_extra_menu=False,
            icon_name='dnfdragora',
            plugin=None
        )
    }
    upd._Updater__update_provider_counts = {
        Updater.DNF_PROVIDER_ID: 6
    }

    class FakeAction:
        def __init__(self):
            self.text = None
            self.icon = None

        def setText(self, text):
            self.text = text

        def setIcon(self, icon):
            self.icon = icon

    upd._tray_update_action = FakeAction()
    upd._tray_open_action = FakeAction()
    upd._Updater__load_qicon = lambda name, icon_dir=None: f"icon:{name}"

    upd._Updater__refresh_dnf_action_presentation()

    assert upd._tray_update_action.text == 'Update (6)'
    assert upd._tray_update_action.icon == 'icon:dnfdragora'
    assert upd._tray_open_action.icon == 'icon:dnfdragora'
