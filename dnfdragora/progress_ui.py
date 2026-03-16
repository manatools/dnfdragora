from __future__ import print_function
from __future__ import absolute_import

import datetime
import os
import logging
import manatools.aui.yui as MUI

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

    # Fixed-width phase badges used in the log (exactly 6 chars)
    _PHASES = {
        'dl_start':   '[  DL ]',
        'dl_ok':      '[ DL✓ ]',
        'dl_exists':  '[ DL= ]',
        'dl_err':     '[ DL✗ ]',
        'verify':     '[ VFY ]',
        'prep':       '[PREP ]',
        'elem':       '[ PKG ]',
        'inst':       '[INST ]',
        'inst_ok':    '[INST✓]',
        'upd':        '[ UPD ]',
        'upd_ok':     '[ UPD✓]',
        'rm':         '[  RM ]',
        'rm_ok':      '[ RM✓ ]',
        'script':     '[SCRP ]',
        'script_ok':  '[SCRP✓]',
        'script_err': '[SCRP✗]',
        'complete':   '[DONE✓]',
        'error':      '[ERR! ]',
    }

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
        """Show this dialog and hide the main application window."""
        self._set_main_window_visible(False)

    def close(self):
        """Destroy the popup and restore the main application window."""
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
        self._close_button.setEnabled(True)
        self._update_summary()

    def handle_event(self, event):
        """
        Process a widget event from this dialog.

        Returns ``True`` when the caller should close the dialog (user clicked
        Close or dismissed the window).
        """
        widget = event.widget()
        if widget == self._close_button:
            return True
        if widget == self._save_button:
            self._save_log()
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
            self._append('dl_ok', f"{description}  OK")
        elif status == 1:
            self._append('dl_exists', f"{description}  already cached")
        else:
            self._append('dl_err',
                         f"{description}  ERROR: {error or '?'}")
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
        self._current_label.setValue(f"{action_str}: {nevra}")
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
        self._append('script', f"{nevra}  [{scriptlet_type}]")
        self._current_label.setValue(
            _("Scriptlet: %(n)s  [%(t)s]") % {'n': nevra, 't': scriptlet_type})

    def on_script_stop(self, nevra, scriptlet_type, return_code):
        if return_code == 0:
            self._append('script_ok',
                         f"{nevra}  [{scriptlet_type}]  rc=0")
        else:
            self._append('script_err',
                         f"{nevra}  [{scriptlet_type}]  rc={return_code}")

    def on_script_error(self, nevra, scriptlet_type, return_code):
        self._append('script_err',
                     f"{nevra}  [{scriptlet_type}]  ERROR rc={return_code}")
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
        min_size = self.factory.createMinSize(self._dialog, 80, 30)
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

        # ── Log view ────────────────────────────────────────────────────
        self._log_view = self.factory.createLogView(
            vbox, _("Transaction log"), 20, 2000)
        self._log_view.setStretchable(MUI.YUIDimension.YD_HORIZ, True)
        self._log_view.setStretchable(MUI.YUIDimension.YD_VERT, True)

        # ── Bottom bar: stats + buttons ────────────────────────────────
        bottom_hbox = self.factory.createHBox(vbox)
        self._summary_label = self.factory.createLabel(
            bottom_hbox, _("Running…"))
        self._summary_label.setStretchable(MUI.YUIDimension.YD_HORIZ, True)
        self._save_button = self.factory.createIconButton(
            bottom_hbox, 'document-save', _("&Save log…"))
        self._close_button = self.factory.createIconButton(
            bottom_hbox, 'window-close', _("&Close"))
        self._close_button.setEnabled(False)
        MUI.YUI.app().setApplicationIcon(self._icon)

    def _ts(self):
        """Current time as HH:MM:SS string for log entries."""
        return datetime.datetime.now().strftime("%H:%M:%S")

    def _append(self, phase_key, text):
        """Append one timestamped line to the log view."""
        badge = self._PHASES.get(phase_key, '[     ]')
        line = f"[{self._ts()}] {badge} {text}"
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

    def _set_main_window_visible(self, visible):
        """Show or hide the main application window."""
        try:
            self.parent.dialog.setVisible(visible)
        except Exception:
            logger.error("_set_main_window_visible: setVisible not available")
        # Fallback: enable/disable
        try:
            self.parent.dialog.setEnabled(visible)
        except Exception:
            pass

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
            self._append('elem', f"Log saved → {path}")
        except Exception as exc:
            logger.error("TransactionProgressDialog._save_log: %s", exc)
            self._append('error', f"Save failed: {exc}")
