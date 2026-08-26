from __future__ import print_function
from __future__ import absolute_import

import datetime
import os
import logging
from gettext import gettext as _
import manatools.aui.yui as MUI
import manatools.ui.common as common

logger = logging.getLogger('dnfdragora.progress_ui')

def _format_size(size_bytes):
    """Return a human-readable byte count string."""
    if size_bytes <= 0:
        return "  0 B "
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size_bytes < 1024.0:
            return f"{size_bytes:6.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:6.1f} TB"

class ProgressBar:

    def __init__(self, main_dialog, layout):
        self.factory = MUI.YUI.widgetFactory()

        self.main_dialog = main_dialog
        self.layout = layout
        vbox = self.factory.createVBox(layout)
        hbox = self.factory.createHBox(vbox)
        self.info_widget = self.factory.createLabel(hbox, "")
        self.info_widget.setStretchable( MUI.YUIDimension.YD_HORIZ, True )
        self.info_sub_widget = self.factory.createLabel(hbox, "")
        self.info_sub_widget.setStretchable( MUI.YUIDimension.YD_HORIZ, True )
        self.progressbar = self.factory.createProgressBar(vbox, "")
        self.progressbar.setStretchable( MUI.YUIDimension.YD_HORIZ, True )
        # Start hidden; set_progress() will show the bar when activity begins.
        self.__setVisible(False)

    def info(self, text) :
        self.info_widget.setValue(text)

    def info_sub(self, text) :
        self.info_sub_widget.setValue(text)

    def set_progress(self, frac, label=None) :
        """Update the progress bar value and make the bar visible.

        The bar is always shown when this method is called, regardless of the
        fraction value.  The only way to hide the bar is through reset_all().
        This ensures visibility both at the very start (frac=0) and at
        completion (frac=1), avoiding the flicker caused by immediately hiding
        on boundary values.
        """
        if label is not None:
            self.progressbar.setLabel(label)
        val = self.progressbar.value()
        newval = int(100*frac)
        if (val != newval) :
            self.progressbar.setValue(newval)
        # Always show while progress is being reported; hiding is done via reset_all().
        self.__setVisible(True)

    def reset_all(self) :
        """Clear all labels, reset the bar to zero, and hide all widgets."""
        self.__setVisible(False)
        self.info_widget.setValue('')
        self.info_sub_widget.setValue('')
        self.progressbar.setLabel('')
        self.progressbar.setValue(0)

    def __setVisible(self, on: bool = True):
        self.info_widget.setVisible(bool(on))
        self.info_sub_widget.setVisible(bool(on))
        self.progressbar.setVisible(bool(on))

    def setHelpText(self, help_text: str):    
        self.progressbar.setHelpText(help_text)


class TransactionProgressDialog:
    """
    Specialized popup dialog displayed during the RunTransaction phase.

    While this dialog is open the main dnfdragora window is hidden so the
    user only sees the transaction progress.  All download, verification,
    installation, removal and scriptlet events are recorded in a scrollable
    log.  A global progress bar and a per-package progress bar keep the user
    informed at all times.

    Life-cycle
    ----------
    1. `open()` — show the popup, hide the main window.
    2. All ``_On*`` handlers in ``ui.py`` call the corresponding feed method
       (e.g. `on_download_start`, `on_action_start`, …).
    3. `mark_complete(success)` — enable the Close button; the transaction
       is over but the dialog stays for the user to review the log.
    4. `handle_event(event)` — called from ``handleevent``; returns `True`
       when the dialog should be closed (Close button pressed or window X).
    5. `close()` — destroy the popup, show the main window again.

    The ``dialog`` property exposes the underlying ``YDialog`` so that
    ``handleevent`` can switch ``waitForEvent`` to this dialog once the
    transaction is running.
    """

    # Localized phase labels shown in the log.
    _PHASES = {
        'dl_start':   _('Download start'),
        'dl_ok':      _('Downloaded'),
        'dl_exists':  _('Already cached'),
        'dl_err':     _('Download error'),
        'verify':     _('Verify'),
        'prep':       _('Prepare'),
        'elem':       _('Package'),
        'inst':       _('Install'),
        'inst_ok':    _('Installed'),
        'upd':        _('Upgrade'),
        'upd_ok':     _('Upgraded'),
        'rm':         _('Remove'),
        'rm_ok':      _('Removed'),
        'script':     _('Scriptlet'),
        'script_ok':  _('Scriptlet done'),
        'script_err': _('Scriptlet error'),
        'complete':   _('Completed'),
        'error':      _('Error'),
    }
    _DIALOG_MIN_WIDTH = 800
    _DIALOG_MIN_HEIGHT_WITH_LOG = 500
    _DIALOG_MIN_HEIGHT_NO_LOG = 240

    def __init__(self, parent):
        """
        Parameters
        ----------
        parent : mainGui
            The main application window (provides ``factory``, ``dialog`` …).
        """
        self.parent = parent
        self.factory = parent.factory
        self._icon = parent.icon
        self._complete = False
        self._success = None
        self._cancel_requested = False
        self._pkg_done = 0
        self._pkg_total = 0
        self._errors = 0
        self._log_lines = []          # plain-text lines for saving to file
        self._action_map = {}         # nevra → last action string (for Stop events)

        # Widgets — populated by _build_dialog()
        self._dialog = None
        self._title_label = None
        self._packages_label = None
        self._global_bar = None
        self._current_label = None
        self._current_bar = None
        self._log_view = None
        self._log_frame = None
        self._log_content = None
        self._log_visible = True
        self._summary_label = None
        self._save_button = None
        self._close_button = None

        self._build_dialog()

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def dialog(self):
        """The underlying ``YDialog`` used for event polling."""
        return self._dialog

    def open(self):
        """Show this dialog and disable the main application window."""
        self._dialog.open()
        self._apply_log_visibility(bool(self._log_frame.value()), persist=False)
        self._set_main_window_visible(False)

    def close(self):
        """Destroy the popup and re-enable the main application window."""
        if self._dialog is not None:
            try:
                self._dialog.destroy()
            except Exception:
                pass
            self._dialog = None
        self._set_main_window_visible(True)

    def mark_complete(self, success=True):
        """
        Called after ``OnTransactionAfterComplete``.

        Enables the Close button and finalises the log.
        """
        self._complete = True
        self._success = success
        phase = 'complete' if success else 'error'
        msg = (_("Transaction completed successfully")
               if success else _("Transaction completed with errors"))
        self._append(phase, msg)
        self._title_label.setValue(
            _("Transaction completed") + (" ✓" if success else " — errors"))
        self._current_label.setValue(msg)
        self._current_bar.setValue(100 if success else 0)
        self._global_bar.setValue(100)
        self._close_button.setLabel(_("&Close"))
        self._close_button.setEnabled(True)
        self._update_summary()

    def mark_offline_scheduled(self, finish_action='reboot'):
        """Mark dialog as ready to close after scheduling offline transaction."""
        self._complete = True
        self._success = True
        action = finish_action if finish_action in ('reboot', 'poweroff') else 'reboot'
        msg = _("Offline transaction scheduled. Reboot or power off to continue on next startup.")
        self._append('complete', msg)
        self._title_label.setValue(_("Offline transaction scheduled"))
        self._current_label.setValue(msg)
        self._current_bar.setValue(100)
        self._global_bar.setValue(100)
        self._close_button.setLabel(_("&Close"))
        self._close_button.setEnabled(True)
        self._update_summary()

    def handle_event(self, event):
        """
        Process a widget event from this dialog.

        Returns ``True`` when the caller should close the dialog (user clicked
        Close or dismissed the window).
        """
        widget = event.widget()
        # Some backends emit the inner checkbox widget event instead of the
        # frame itself. Keep log visibility in sync by observing current value.
        current_log_visibility = bool(self._log_frame.value())
        if current_log_visibility != self._log_visible:
            self._apply_log_visibility(current_log_visibility, persist=True)
        if widget == self._close_button:
            return self.request_close()
        if widget == self._save_button:
            self._save_log()
        if widget == self._log_frame:
            self._on_log_frame_toggled()
        return False

    def request_close(self):
        """Handle user close/cancel requests during transaction execution.

        Behavior:
        - If transaction is complete, allow closing.
        - If still running, request Goal.cancel and keep dialog open.
        - On cancel refusal/error, keep dialog open and show the reason.
        """
        if self._complete:
            return True

        if getattr(self.parent, '_offline_transaction_running', False):
            if getattr(self.parent, '_offline_transaction_prepared', False):
                self._append('complete', _("Offline transaction is scheduled. You can close this window."))
                self._close_button.setEnabled(True)
                return True
            self._append('prep', _("Offline transaction is being prepared. Please wait..."))
            return False

        if self._cancel_requested:
            self._append('prep', _("Cancellation already requested; waiting..."))
            return False

        try:
            MUI.YUI.app().busyCursor()
            success, error_msg = self.parent.backend.CancelTransaction(sync=True)
        except Exception as err:
            logger.exception("CancelTransaction failed: %s", err)
            self._append('error', _("Cancellation request failed: %(err)s") % {'err': str(err)})
            return False
        finally:
            MUI.YUI.app().normalCursor()

        if success:
            self._cancel_requested = True
            self._append('prep', _("Cancellation requested; waiting for transaction to stop"))
            self._title_label.setValue(_("Cancelling transaction..."))
            self._current_label.setValue(_("Waiting for backend to stop transaction"))
            logger.info("CancelTransaction success")
            return True

        msg = error_msg if error_msg else _("Cancellation refused by backend")
        logger.warning("CancelTransaction refused: %s", msg)
        self._append('error', _("Cancellation refused: %(msg)s") % {'msg': msg})
        return False

    # ── Event feed methods (called from ui.py _On* handlers) ─────────────

    def on_download_start(self, download_id, description, total_to_download):
        size_str = _format_size(total_to_download)
        self._append('dl_start', f"{description}  {size_str}")
        self._current_label.setValue(
            _("Downloading:  %(d)s") % {'d': description})
        self._current_bar.setValue(0)

    def on_download_progress(self, download_id, downloaded, total_to_download):
        if total_to_download > 0:
            self._current_bar.setValue(
                int(downloaded / total_to_download * 100))

    def on_download_end(self, download_id, description, status, error):
        if status == 0:
            self._append('dl_ok', _("%(desc)s  completed") % {'desc': description})
        elif status == 1:
            self._append('dl_exists', _("%(desc)s  already cached") % {'desc': description})
        else:
            self._append('dl_err',
                         _("%(desc)s  failed: %(err)s") % {
                             'desc': description,
                             'err': error or '?',
                         })
            self._errors += 1
            self._update_summary()

    def on_verify_start(self, total):
        self._append('verify',
                     _("Verifying %(n)d packages") % {'n': total})
        self._current_label.setValue(_("Verifying packages"))
        self._current_bar.setValue(0)

    def on_verify_progress(self, processed, total):
        if total > 0:
            self._current_bar.setValue(int(processed / total * 100))

    def on_verify_stop(self, total):
        self._current_bar.setValue(100)

    def on_transaction_start(self, total):
        if total > 0:
            self._pkg_total = total
        self._append('prep',
                     _("Preparing transaction: %(n)d packages") % {'n': total})
        self._current_label.setValue(_("Preparing transaction"))
        self._update_stats()
    def on_transaction_progress(self, processed, total):
        if total > 0:
            self._current_bar.setValue(int(processed / total * 100))
    def on_transaction_stop(self, total):
        self._current_bar.setValue(100)

    def on_elem_progress(self, nevra, processed, total):
        if total > 0 and self._pkg_total == 0:
            self._pkg_total = total
        self._pkg_done = max(self._pkg_done, processed)
        self._update_stats()
        self._current_label.setValue(
            _("Processing: %(n)s") % {'n': nevra})

    def on_action_start(self, nevra, action_str):
        self._action_map[nevra] = action_str
        phase = self._action_to_phase(action_str)
        self._append(phase, f"{nevra}")
        self._current_label.setValue(
            _("%(action)s: %(nevra)s") % {
                'action': self._human_action(action_str),
                'nevra': nevra,
            })
        self._current_bar.setValue(0)

    def on_action_progress(self, nevra, processed, total):
        if total > 0 and processed > 0:
            self._current_bar.setValue(int(processed / total * 100))

    def on_action_stop(self, nevra):
        action_str = self._action_map.pop(nevra, '')
        phase = self._action_to_phase(action_str) + '_ok'
        if phase not in self._PHASES:
            phase = 'elem'
        self._append(phase, f"{nevra}  ✓")
        self._pkg_done += 1
        self._update_stats()

    def on_script_start(self, nevra, scriptlet_type):
        scriptlet_human = self._human_scriptlet_type(scriptlet_type)
        self._append('script', _("%(nevra)s  [%(kind)s]") % {
            'nevra': nevra,
            'kind': scriptlet_human,
        })
        self._current_label.setValue(
            _("Scriptlet: %(n)s  [%(t)s]") % {'n': nevra, 't': scriptlet_human})

    def on_script_stop(self, nevra, scriptlet_type, return_code):
        scriptlet_human = self._human_scriptlet_type(scriptlet_type)
        if return_code == 0:
            self._append('script_ok',
                         _("%(nevra)s  [%(kind)s]  %(status)s") % {
                             'nevra': nevra,
                             'kind': scriptlet_human,
                             'status': self._human_exit_status(return_code),
                         })
        else:
            self._append('script_err',
                         _("%(nevra)s  [%(kind)s]  %(status)s") % {
                             'nevra': nevra,
                             'kind': scriptlet_human,
                             'status': self._human_exit_status(return_code),
                         })

    def on_script_error(self, nevra, scriptlet_type, return_code):
        scriptlet_human = self._human_scriptlet_type(scriptlet_type)
        self._append('script_err',
                     _("%(nevra)s  [%(kind)s]  failed: %(status)s") % {
                         'nevra': nevra,
                         'kind': scriptlet_human,
                         'status': self._human_exit_status(return_code),
                     })
        self._errors += 1
        self._update_summary()

    def on_error(self, message):
        self._append('error', message)
        self._errors += 1
        self._update_summary()

    # ── Internal helpers ──────────────────────────────────────────────────

    def _build_dialog(self):
        """Construct the popup dialog with all widgets."""
        self._dialog = self.factory.createPopupDialog()
        self._log_visible = self._read_log_visibility_pref(default=True)
        min_height = (self._DIALOG_MIN_HEIGHT_WITH_LOG
                      if self._log_visible else self._DIALOG_MIN_HEIGHT_NO_LOG)
        # Keep width readable for full NEVRA strings. Height is adaptive:
        # compact when the log is hidden, larger when the log is visible.
        min_size = self.factory.createMinSize(
            self._dialog, self._DIALOG_MIN_WIDTH, min_height)
        vbox = self.factory.createVBox(min_size)

        # ── Title ──────────────────────────────────────────────────────
        title_hbox = self.factory.createHBox(vbox)
        self._title_label = self.factory.createLabel(
            title_hbox, _("Transaction in progress…"))
        self._title_label.setStretchable(MUI.YUIDimension.YD_HORIZ, True)

        # ── Global progress (package counter + bar) ────────────────────
        global_hbox = self.factory.createHBox(vbox)
        self.factory.createLabel(global_hbox, _("Packages:"))
        self._packages_label = self.factory.createLabel(global_hbox,
                                                        "  0 / 0  ")
        self._global_bar = self.factory.createProgressBar(global_hbox, "")
        self._global_bar.setStretchable(MUI.YUIDimension.YD_HORIZ, True)

        # ── Current operation ──────────────────────────────────────────
        current_hbox = self.factory.createHBox(vbox)
        self.factory.createLabel(current_hbox, _("Current:"))
        self._current_label = self.factory.createLabel(current_hbox, "")
        self._current_label.setStretchable(MUI.YUIDimension.YD_HORIZ, True)
        self._current_bar = self.factory.createProgressBar(vbox, "")
        self._current_bar.setStretchable(MUI.YUIDimension.YD_HORIZ, True)

        # ── Log view (collapsible) ──────────────────────────────────────
        self._log_frame = self.factory.createCheckBoxFrame(
            vbox, _("Show transaction log"), self._log_visible)
        self._log_frame.setNotify(True)
        self._log_frame.setStretchable(MUI.YUIDimension.YD_HORIZ, True)
        self._log_content = self.factory.createVBox(self._log_frame)
        self._log_view = self.factory.createLogView(
            self._log_content, _("Transaction log"), 20, storedLines=2000,
            focus=MUI.YLogViewFocus.TAIL, reverse=False)
        self._log_view.setStretchable(MUI.YUIDimension.YD_HORIZ, True)
        self._log_view.setStretchable(MUI.YUIDimension.YD_VERT, True)
        self._apply_log_visibility(self._log_visible, persist=False)

        # ── Bottom bar: stats + buttons ────────────────────────────────
        bottom_hbox = self.factory.createHBox(vbox)
        self._summary_label = self.factory.createLabel(
            bottom_hbox, _("Running…"))
        self._summary_label.setStretchable(MUI.YUIDimension.YD_HORIZ, True)
        self._save_button = self.factory.createIconButton(
            bottom_hbox, 'document-save', _("&Save log…"))
        self._close_button = self.factory.createIconButton(
            bottom_hbox, 'window-close', _("&Cancel"))
        # Must be active during download/running to let user request Goal.cancel.
        # Cancel a transaction is only possible when downloading packages, 
        # so at the very beginning of the running transaction, let's disable the Close button 
        # to avoid problems (for instance, PCLinuxOS hangs running a sync cancel).
        self._close_button.setEnabled(False)
        MUI.YUI.app().setApplicationIcon(self._icon)

    def _ts(self):
        """Current time as HH:MM:SS string for log entries."""
        return datetime.datetime.now().strftime("%H:%M:%S")

    def _append(self, phase_key, text):
        """Append one timestamped line to the log view."""
        phase = self._PHASES.get(phase_key, _('Info'))
        line = _("[%(time)s] [%(phase)s] %(text)s") % {
            'time': self._ts(),
            'phase': phase,
            'text': text,
        }
        self._log_lines.append(line)
        self._log_view.appendLines(line)

    def _update_stats(self):
        """Refresh the package counter label and global progress bar."""
        self._packages_label.setValue(
            f"  {self._pkg_done} / {self._pkg_total}  ")
        if self._pkg_total > 0:
            self._global_bar.setValue(
                int(self._pkg_done / self._pkg_total * 100))
        self._update_summary()

    def _update_summary(self):
        """Refresh the bottom summary label."""
        if self._complete:
            status = (_("Completed ✓") if self._success
                      else _("Completed with errors"))
        else:
            status = _("Running…")
        err_part = (f"   {_('Errors')}: {self._errors}"
                    if self._errors else "")
        self._summary_label.setValue(
            f"{status}   {_('Done')}: {self._pkg_done}/{self._pkg_total}"
            f"{err_part}")

    @staticmethod
    def _action_to_phase(action_str):
        """Map a dnf5 action string to a phase key for _PHASES."""
        _MAP = {
            'Install':   'inst',
            'Upgrade':   'upd',
            'Downgrade': 'inst',
            'Reinstall': 'inst',
            'Remove':    'rm',
            'Cleanup':   'rm',
            'Replaced':  'rm',
        }
        return _MAP.get(action_str, 'elem')

    @staticmethod
    def _human_action(action_str):
        """Return a translatable label for a backend action string."""
        action_map = {
            'Install': _('Install'),
            'Upgrade': _('Upgrade'),
            'Downgrade': _('Downgrade'),
            'Reinstall': _('Reinstall'),
            'Remove': _('Remove'),
            'Cleanup': _('Cleanup'),
            'Replaced': _('Replaced'),
        }
        return action_map.get(action_str, action_str)

    @staticmethod
    def _human_scriptlet_type(scriptlet_type):
        """Return a readable label for dnf/rpm scriptlet type tokens."""
        token = str(scriptlet_type or '').strip()
        normalized = token.lower().strip('%').replace('-', '').replace('_', '')
        kind_map = {
            'pre': _('Pre script'),
            'post': _('Post script'),
            'prein': _('Pre-install script'),
            'postin': _('Post-install script'),
            'preun': _('Pre-uninstall script'),
            'postun': _('Post-uninstall script'),
            'pretrans': _('Pre-transaction script'),
            'posttrans': _('Post-transaction script'),
            'triggerin': _('Install trigger'),
            'triggerun': _('Uninstall trigger'),
            'triggerpostun': _('Post-uninstall trigger'),
            'verify': _('Verification script'),
        }
        if normalized in kind_map:
            return kind_map[normalized]
        if token:
            return _("Unknown scriptlet (%(token)s)") % {'token': token}
        return _('Unknown scriptlet')

    @staticmethod
    def _human_exit_status(return_code):
        """Return a readable and translatable scriptlet exit status text."""
        if return_code == 0:
            return _('completed successfully')
        return _("failed with exit code %(code)s") % {'code': return_code}

    def _on_log_frame_toggled(self):
        """Apply and persist the user choice for log-frame visibility."""
        try:
            self._apply_log_visibility(bool(self._log_frame.value()), persist=True)
            logger.debug("Transaction log visibility changed to %s", self._log_visible)
        except Exception as exc:
            logger.exception("Failed to toggle/persist transaction log visibility: %s", exc)

    def _apply_log_visibility(self, visible, persist=True):
        """Apply log visibility in UI and optionally persist it."""
        self._log_visible = bool(visible)
        self._log_frame.showContent(self._log_visible)
        # Explicit visibility update helps backends that do not relayout
        # CheckBoxFrame content reliably on toggle.
        if self._log_content is not None:
            self._log_content.setVisible(self._log_visible)
            self._log_content.setWeight(
                MUI.YUIDimension.YD_VERT, 100 if self._log_visible else 1)
        if self._log_view is not None:
            self._log_view.setVisible(self._log_visible)
        if self._log_frame is not None:
            self._log_frame.setWeight(
                MUI.YUIDimension.YD_VERT, 100 if self._log_visible else 1)
            self._log_frame.setStretchable(MUI.YUIDimension.YD_VERT, self._log_visible)
        if persist:
            self._save_log_visibility_pref(self._log_visible)

    def _read_log_visibility_pref(self, default=True):
        """Read persisted visibility preference for transaction log details."""
        try:
            config = getattr(self.parent, 'config', None)
            if config is None:
                return default
            prefs = config.userPreferences or {}
            settings = prefs.get('settings') or {}
            tx = settings.get('transaction_progress') or {}
            return bool(tx.get('show_log', default))
        except Exception as exc:
            logger.exception("Failed reading transaction log visibility preference: %s", exc)
            return default

    def _save_log_visibility_pref(self, value):
        """Persist visibility preference for transaction log details."""
        try:
            config = getattr(self.parent, 'config', None)
            if config is None:
                logger.debug("Transaction log visibility not saved: config is unavailable")
                return
            prefs = config.userPreferences
            if not isinstance(prefs, dict):
                prefs = {}
                config._userPrefs = prefs
            settings = prefs.setdefault('settings', {})
            tx = settings.setdefault('transaction_progress', {})
            tx['show_log'] = bool(value)
            config.saveUserPreferences()
        except Exception as exc:
            logger.exception("Failed saving transaction log visibility preference: %s", exc)

    def _set_main_window_visible(self, visible):
        """Keep main window visible and only toggle interactivity.

        Hiding the main window can break modal-child behavior and can remove
        the application icon from taskbar on some backends/window managers.
        """
        try:
            self.parent.dialog.setEnabled(visible)
        except Exception as exc:
            logger.exception("Failed to set main window enabled=%s: %s", visible, exc)

    def _save_log(self):
        """Ask the user for a file path and write the log there."""
        try:
            default = os.path.join(
                os.path.expanduser("~"),
                "dnfdragora-transaction-"
                + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                + ".log")
            path = MUI.YUI.app().askForSaveFileName(
                default, "*.log",
                _("Save transaction log"))
            if not path:
                return
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write("# dnfdragora transaction log\n")
                fh.write(
                    f"# {datetime.datetime.now().isoformat()}\n\n")
                for line in self._log_lines:
                    fh.write(line + "\n")
            self._append('elem', _("Log saved to %(path)s") % {'path': path})
        except Exception as exc:
            logger.error("TransactionProgressDialog._save_log: %s", exc)
            self._append('error', _("Saving log failed: %(err)s") % {'err': exc})
