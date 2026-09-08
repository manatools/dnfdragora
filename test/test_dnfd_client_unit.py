#!/usr/bin/env python3
"""Unit tests for dnfdragora.dnfd_client with local fakes/mocks.

These tests are runtime unit tests (not source-string checks):
- compatibility of API routing/proxy dispatch
- async single-flight guard behavior
- sync wrappers and argument adaptation
- basic error mapping safety paths
"""

import os
import sys
import types
import threading
from queue import SimpleQueue

# Ensure imports come from this workspace copy of dnfdragora, not site-packages.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _install_dependency_stubs():
    """Install minimal stubs for external modules used at import time."""
    if 'dbus' not in sys.modules:
        dbus_mod = types.ModuleType('dbus')

        class _DBusString(str):
            pass

        class _DBusObjectPath(str):
            pass

        class _DBusSignature(str):
            pass

        class _DBusBoolean(int):
            pass

        class _DBusArray(list):
            def __init__(self, values=(), signature=None):
                super().__init__(values)
                self.signature = signature

        class _DBusStruct(tuple):
            pass

        class _DBusDictionary(dict):
            def __init__(self, values=(), signature=None):
                super().__init__(values)
                self.signature = signature

        class _DBusUnixFd(int):
            pass

        dbus_mod.String = _DBusString
        dbus_mod.ObjectPath = _DBusObjectPath
        dbus_mod.Signature = _DBusSignature
        dbus_mod.Boolean = _DBusBoolean
        dbus_mod.Int64 = int
        dbus_mod.UInt64 = int
        dbus_mod.Int32 = int
        dbus_mod.UInt32 = int
        dbus_mod.Int16 = int
        dbus_mod.UInt16 = int
        dbus_mod.Byte = int
        dbus_mod.Double = float
        dbus_mod.Array = _DBusArray
        dbus_mod.Struct = _DBusStruct
        dbus_mod.Dictionary = _DBusDictionary
        dbus_mod.UnixFd = _DBusUnixFd
        dbus_mod.types = types.SimpleNamespace(UnixFd=_DBusUnixFd)

        dbus_mod.Interface = lambda obj, dbus_interface=None: obj

        class _SystemBus:
            def __init__(self, mainloop=None):
                self.mainloop = mainloop

            def get_object(self, *_args, **_kwargs):
                return object()

            def remove_signal_receiver(self, *_args, **_kwargs):
                return None

        dbus_mod.SystemBus = _SystemBus

        dbus_mainloop = types.ModuleType('dbus.mainloop')
        dbus_mainloop_glib = types.ModuleType('dbus.mainloop.glib')
        dbus_mainloop_glib.DBusGMainLoop = lambda set_as_default=True: object()

        dbus_mod.mainloop = dbus_mainloop
        dbus_mainloop.glib = dbus_mainloop_glib

        sys.modules['dbus'] = dbus_mod
        sys.modules['dbus.mainloop'] = dbus_mainloop
        sys.modules['dbus.mainloop.glib'] = dbus_mainloop_glib

    if 'libdnf5' not in sys.modules:
        libdnf5_mod = types.ModuleType('libdnf5')
        libdnf5_mod.base = types.SimpleNamespace(Base=lambda: object())
        libdnf5_mod.comps = types.SimpleNamespace(GroupQuery=lambda *_args, **_kwargs: [])
        sys.modules['libdnf5'] = libdnf5_mod

    if 'gi' not in sys.modules:
        gi_mod = types.ModuleType('gi')
        gi_repo = types.ModuleType('gi.repository')

        class _BusType:
            SYSTEM = 0

        gi_repo.Gio = types.SimpleNamespace(
            BusType=_BusType,
            bus_get_sync=lambda *_args, **_kwargs: object(),
            DBusProxy=types.SimpleNamespace(
                new_sync=lambda *a, **k: object(),
                new=lambda *a, **k: None,
            ),
        )
        gi_repo.GLib = types.SimpleNamespace()
        gi_repo.GObject = types.SimpleNamespace()
        gi_mod.repository = gi_repo
        sys.modules['gi'] = gi_mod
        sys.modules['gi.repository'] = gi_repo


_install_dependency_stubs()

from dnfdragora import dnfd_client

# dnfdragora.dnfd_client uses gettext-installed _ in async guard path.
if not hasattr(dnfd_client, '_'):
    dnfd_client._ = lambda text: text


class _FakeProxy:
    def __init__(self, **methods):
        for name, fn in methods.items():
            setattr(self, name, fn)



def _make_client_stub():
    """Create a Client instance without running its heavy __init__."""
    c = object.__new__(dnfd_client.Client)
    c._async_lock = threading.Lock()
    c._sent = False
    c._data = {'cmd': None}
    c.eventQueue = SimpleQueue()

    c.iface_rpm = object()
    c.iface_repo = object()
    c.iface_advisory = object()
    c.iface_history = object()
    c.iface_base = object()
    c.iface_goal = object()
    c.iface_offline = object()
    c.dbus_org = dnfd_client.DNFDAEMON_BUS_NAME
    c.session_path = None
    c._comps_base = None
    c._comps_base_lock = threading.RLock()

    c.proxyMethod = {
        'GetPackages_fd': 'list_fd',
        'GetPackages': 'list',
        'Search': 'list',
        'RunTransaction': 'do_transaction',
        'Advisories': 'list',
    }
    return c


def test_proxy_routes_commands_to_expected_interfaces():
    c = _make_client_stub()
    assert c.Proxy('Search') is c.iface_rpm
    assert c.Proxy('GetRepositories') is c.iface_repo
    assert c.Proxy('Advisories') is c.iface_advisory
    assert c.Proxy('HistoryRecentChanges') is c.iface_history
    assert c.Proxy('CleanCache') is c.iface_base
    assert c.Proxy('BuildTransaction') is c.iface_goal
    assert c.Proxy('OfflineGetStatus') is c.iface_offline


def test_proxy_unknown_command_returns_none():
    c = _make_client_stub()
    assert c.Proxy('TotallyUnknownCommand') is None


def test_run_dbus_sync_rejects_missing_proxy():
    c = _make_client_stub()
    c.Proxy = lambda _cmd: None
    try:
        c._run_dbus_sync('Search', {'scope': 'all'})
        assert False, 'Expected DaemonError for missing proxy'
    except dnfd_client.DaemonError as err:
        assert 'No proxy available' in str(err)


def test_run_dbus_sync_rejects_missing_proxy_method_mapping():
    c = _make_client_stub()
    c.Proxy = lambda _cmd: _FakeProxy(list=lambda *_args, **_kwargs: [])
    c.proxyMethod = {}
    try:
        c._run_dbus_sync('Search', {'scope': 'all'})
        assert False, 'Expected DaemonError for missing proxyMethod mapping'
    except dnfd_client.DaemonError as err:
        assert 'No proxyMethod configured' in str(err)


def test_search_sync_adds_required_attrs_and_returns_pkg_ids():
    c = _make_client_stub()

    captured = {}

    def _fake_sync(cmd, options):
        captured['cmd'] = cmd
        captured['options'] = options
        return [
            {
                'name': 'nano',
                'epoch': '0',
                'version': '7.2',
                'release': '1',
                'arch': 'x86_64',
                'repo_id': 'updates',
            }
        ]

    c._run_dbus_sync = _fake_sync

    options = {'scope': 'all', 'package_attrs': ['summary']}
    pkg_ids = c.Search(options, sync=True)

    assert captured['cmd'] == 'Search'
    required = {'name', 'epoch', 'version', 'release', 'arch', 'repo_id'}
    assert required.issubset(set(captured['options']['package_attrs']))
    assert 'summary' in captured['options']['package_attrs']
    assert pkg_ids == ['nano,0,7.2,1,x86_64,updates']


def test_advisories_sync_returns_unpacked_result():
    c = _make_client_stub()
    advisories = [{'advisoryid': 'ADV-1', 'type': 'security'}]
    c._run_dbus_sync = lambda cmd, options: advisories
    out = c.Advisories({'availability': 'all'}, sync=True)
    assert out == advisories


def test_run_transaction_async_uses_infinite_timeout():
    c = _make_client_stub()
    calls = {}

    def _fake_async(cmd, return_value, options, timeout=None):
        calls['cmd'] = cmd
        calls['return_value'] = return_value
        calls['options'] = options
        calls['timeout'] = timeout

    c._run_dbus_async = _fake_async
    c.RunTransaction({'offline': True}, sync=False)

    assert calls['cmd'] == 'RunTransaction'
    assert calls['return_value'] is False
    assert calls['options'] == {'offline': True}
    assert calls['timeout'] == dnfd_client._DBUS_TIMEOUT_INFINITE


def test_async_guard_rejects_second_command_and_emits_event():
    c = _make_client_stub()
    c._sent = True
    c._data = {'cmd': 'GetPackages'}

    c._run_dbus_async('Search', True, {'scope': 'all'})

    evt = c.eventQueue.get_nowait()
    assert evt['event'] == 'Search'
    assert evt['value']['result'] is False
    assert evt['value']['error'] == 'Command in progress'


def test_get_result_getattribute_error_markers_and_success_path():
    c = _make_client_stub()

    no_attr = c._get_result({
        'cmd': 'GetAttribute',
        'result': ':none',
        'error': None,
        'args': ({'package_attrs': ['summary']},),
    })
    assert no_attr['error'] == 'Illegal attribute'

    not_found = c._get_result({
        'cmd': 'GetAttribute',
        'result': ':not_found',
        'error': None,
        'args': ({'package_attrs': ['summary']},),
    })
    assert not_found['error'] == 'Package not found'

    ok = c._get_result({
        'cmd': 'GetAttribute',
        'result': [{'summary': 'tiny editor'}],
        'error': None,
        'args': ({'package_attrs': ['summary']},),
    })
    assert ok['result'] == 'tiny editor'


def test_handle_dbus_error_maps_known_errors_and_fallback():
    c = _make_client_stub()

    c._parse_error = lambda: (c.dbus_org + '.LockedError', 'locked')
    try:
        c._handle_dbus_error(RuntimeError('x'))
        assert False, 'Expected LockedError'
    except dnfd_client.LockedError as err:
        assert str(err) == 'locked'

    c._parse_error = lambda: ('unknown.error', 'boom')
    try:
        c._handle_dbus_error(RuntimeError('fallback'))
        assert False, 'Expected fallback DaemonError'
    except dnfd_client.DaemonError as err:
        assert 'fallback' in str(err)


def test_get_object_proxy_uses_introspect_false():
    c = _make_client_stub()
    captured = {}

    class _Bus:
        def get_object(self, bus_name, object_path, introspect=None):
            captured['bus_name'] = bus_name
            captured['object_path'] = object_path
            captured['introspect'] = introspect
            return object()

    c.bus = _Bus()
    obj = c._get_object_proxy('/org/rpm/dnf/v0')
    assert obj is not None
    assert captured['bus_name'] == dnfd_client.DNFDAEMON_BUS_NAME
    assert captured['object_path'] == '/org/rpm/dnf/v0'
    assert captured['introspect'] is False


def test_get_object_proxy_fallback_when_introspect_kw_not_supported():
    c = _make_client_stub()
    calls = {'count': 0}

    class _Bus:
        def get_object(self, bus_name, object_path, introspect=None):
            calls['count'] += 1
            if calls['count'] == 1:
                raise TypeError('unexpected keyword argument introspect')
            return (bus_name, object_path)

    c.bus = _Bus()
    out = c._get_object_proxy('/org/rpm/dnf/v0')
    assert out == (dnfd_client.DNFDAEMON_BUS_NAME, '/org/rpm/dnf/v0')
    assert calls['count'] == 2


def test_to_session_dbus_options_handles_empty_dict():
    out = dnfd_client.Client._to_session_dbus_options({})
    assert len(dict(out)) == 0


def test_to_session_dbus_options_converts_scalar_values():
    out = dnfd_client.Client._to_session_dbus_options({
        'interactive': True,
        'retry_count': 2,
        'mode': 'default',
    })
    # Keep assertions backend-agnostic against local dbus stubs.
    values = dict(out)
    assert bool(values['interactive']) is True
    assert int(values['retry_count']) == 2
    assert str(values['mode']) == 'default'


def test_run_dbus_sync_coerces_getpackages_options_to_sv_map():
    c = _make_client_stub()
    captured = {}

    def _list_method(options, timeout=None):
        captured['options'] = options
        captured['timeout'] = timeout
        return []

    proxy = _FakeProxy(list=_list_method)
    c.Proxy = lambda _cmd: proxy
    c.proxyMethod = {'GetPackages': 'list'}

    c._run_dbus_sync('GetPackages', {'scope': 'upgrades', 'package_attrs': ['nevra']})

    assert hasattr(captured['options'], 'signature')
    assert captured['options'].signature == 'sv'
    assert captured['timeout'] == 600


def test_run_dbus_async_coerces_getpackages_options_to_sv_map():
    c = _make_client_stub()
    captured = {}

    def _list_method(options, reply_handler=None, error_handler=None, timeout=None):
        captured['options'] = options
        captured['timeout'] = timeout
        if reply_handler is not None:
            reply_handler([])

    proxy = _FakeProxy(list=_list_method)
    c.Proxy = lambda _cmd: proxy
    c.proxyMethod = {'GetPackages': 'list'}

    c._run_dbus_async('GetPackages', True, {'scope': 'upgrades', 'package_attrs': ['nevra']})

    assert hasattr(captured['options'], 'signature')
    assert captured['options'].signature == 'sv'
    assert captured['timeout'] == dnfd_client._DBUS_TIMEOUT_DEFAULT


def test_coerce_dbus_args_handles_getpackages_fd_options():
    c = _make_client_stub()
    args = c._coerce_dbus_args('GetPackages_fd', ({'scope': 'all'},))
    assert len(args) == 1
    assert hasattr(args[0], 'signature')
    assert args[0].signature == 'sv'


def test_wrap_unix_fd_uses_dbus_type_when_available():
    wrapped = dnfd_client.Client._wrap_unix_fd(42)
    assert isinstance(wrapped, int)
    # On real dbus-python this should be dbus.UnixFd or dbus.types.UnixFd.
    assert wrapped.__class__.__name__.lower().endswith('unixfd')
    assert int(wrapped) == 42


def test_coerce_dbus_args_keeps_typed_dbus_dictionary_unchanged():
    c = _make_client_stub()
    typed = dnfd_client.dbus.Dictionary(
        {'upgraded_packages': dnfd_client.dbus.Boolean(True)},
        signature='sv',
    )
    coerced = c._coerce_dbus_args('GetPackages', (typed,))
    assert coerced[0] is typed


def test_run_dbus_sync_coerces_advisories_options_to_sv_map():
    c = _make_client_stub()
    captured = {}

    def _list_method(options, timeout=None):
        captured['options'] = options
        captured['timeout'] = timeout
        return []

    proxy = _FakeProxy(list=_list_method)
    c.Proxy = lambda _cmd: proxy
    c.proxyMethod = {'Advisories': 'list'}

    c._run_dbus_sync('Advisories', {
        'availability': 'available',
        'types': ['security'],
    })

    assert hasattr(captured['options'], 'signature')
    assert captured['options'].signature == 'sv'
    assert captured['timeout'] == 600


def test_run_dbus_async_coerces_advisories_options_to_sv_map():
    c = _make_client_stub()
    captured = {}

    def _list_method(options, reply_handler=None, error_handler=None, timeout=None):
        captured['options'] = options
        captured['timeout'] = timeout
        if reply_handler is not None:
            reply_handler([])

    proxy = _FakeProxy(list=_list_method)
    c.Proxy = lambda _cmd: proxy
    c.proxyMethod = {'Advisories': 'list'}

    c._run_dbus_async('Advisories', True, {
        'availability': 'available',
        'types': ['security'],
    })

    assert hasattr(captured['options'], 'signature')
    assert captured['options'].signature == 'sv'
    assert captured['timeout'] == dnfd_client._DBUS_TIMEOUT_DEFAULT


def test_run_dbus_sync_coerces_distrosync_options_to_sv_map():
    c = _make_client_stub()
    captured = {}

    def _method(specs, options, timeout=None):
        captured['specs'] = specs
        captured['options'] = options
        captured['timeout'] = timeout
        return True

    proxy = _FakeProxy(distro_sync=_method)
    c.Proxy = lambda _cmd: proxy
    c.proxyMethod = {'DistroSync': 'distro_sync'}

    c._run_dbus_sync('DistroSync', ['nano'], {'repo_ids': ['updates']})

    assert captured['specs'] == ['nano']
    assert hasattr(captured['options'], 'signature')
    assert captured['options'].signature == 'sv'
    assert captured['timeout'] == 600


def test_run_dbus_async_coerces_distrosync_options_to_sv_map():
    c = _make_client_stub()
    captured = {}

    def _method(specs, options, reply_handler=None, error_handler=None, timeout=None):
        captured['specs'] = specs
        captured['options'] = options
        captured['timeout'] = timeout
        if reply_handler is not None:
            reply_handler()

    proxy = _FakeProxy(distro_sync=_method)
    c.Proxy = lambda _cmd: proxy
    c.proxyMethod = {'DistroSync': 'distro_sync'}

    c._run_dbus_async('DistroSync', False, ['nano'], {'repo_ids': ['updates']})

    assert captured['specs'] == ['nano']
    assert hasattr(captured['options'], 'signature')
    assert captured['options'].signature == 'sv'
    assert captured['timeout'] == dnfd_client._DBUS_TIMEOUT_DEFAULT


def test_run_dbus_sync_coerces_offlineclean_options_to_sv_map():
    c = _make_client_stub()
    captured = {}

    def _method(options, timeout=None):
        captured['options'] = options
        captured['timeout'] = timeout
        return (True, '')

    proxy = _FakeProxy(clean=_method)
    c.Proxy = lambda _cmd: proxy
    c.proxyMethod = {'OfflineClean': 'clean'}

    c._run_dbus_sync('OfflineClean', {'interactive': False})

    assert hasattr(captured['options'], 'signature')
    assert captured['options'].signature == 'sv'
    assert captured['timeout'] == 600


def test_run_dbus_async_keeps_offline_finish_action_scalar():
    c = _make_client_stub()
    captured = {}

    def _method(action, reply_handler=None, error_handler=None, timeout=None):
        captured['action'] = action
        captured['timeout'] = timeout
        if reply_handler is not None:
            reply_handler(True, '')

    proxy = _FakeProxy(set_finish_action=_method)
    c.Proxy = lambda _cmd: proxy
    c.proxyMethod = {'OfflineSetFinishAction': 'set_finish_action'}

    c._run_dbus_async('OfflineSetFinishAction', True, 'reboot')

    assert captured['action'] == 'reboot'
    assert captured['timeout'] == dnfd_client._DBUS_TIMEOUT_DEFAULT


if __name__ == '__main__':
    tests = [
        test_proxy_routes_commands_to_expected_interfaces,
        test_proxy_unknown_command_returns_none,
        test_run_dbus_sync_rejects_missing_proxy,
        test_run_dbus_sync_rejects_missing_proxy_method_mapping,
        test_search_sync_adds_required_attrs_and_returns_pkg_ids,
        test_advisories_sync_returns_unpacked_result,
        test_run_transaction_async_uses_infinite_timeout,
        test_async_guard_rejects_second_command_and_emits_event,
        test_get_result_getattribute_error_markers_and_success_path,
        test_handle_dbus_error_maps_known_errors_and_fallback,
        test_get_object_proxy_uses_introspect_false,
        test_get_object_proxy_fallback_when_introspect_kw_not_supported,
        test_to_session_dbus_options_handles_empty_dict,
        test_to_session_dbus_options_converts_scalar_values,
        test_run_dbus_sync_coerces_getpackages_options_to_sv_map,
        test_run_dbus_async_coerces_getpackages_options_to_sv_map,
        test_coerce_dbus_args_handles_getpackages_fd_options,
        test_wrap_unix_fd_uses_dbus_type_when_available,
        test_coerce_dbus_args_keeps_typed_dbus_dictionary_unchanged,
        test_run_dbus_sync_coerces_advisories_options_to_sv_map,
        test_run_dbus_async_coerces_advisories_options_to_sv_map,
        test_run_dbus_sync_coerces_distrosync_options_to_sv_map,
        test_run_dbus_async_coerces_distrosync_options_to_sv_map,
        test_run_dbus_sync_coerces_offlineclean_options_to_sv_map,
        test_run_dbus_async_keeps_offline_finish_action_scalar,
    ]

    passed = 0
    for test in tests:
        test()
        passed += 1

    print(f'OK: {passed}/{len(tests)} dnfd_client unit checks passed')
