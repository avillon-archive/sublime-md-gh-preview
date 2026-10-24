# -*- coding: utf-8 -*-
"""Sublime Text entry point: commands and thin event listeners over mdgh.controller."""
import os
import sys

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib')
_VENDORED = ('markdown_it', 'mdurl', 'mdit_py_plugins')


def _use_vendored_lib():
    # Another package may already have imported its own copy of these names; the parser
    # setup is version pinned, so those entries are dropped and ours imported instead.
    # The other package keeps the module objects it already holds.
    lib = os.path.normcase(_LIB) + os.sep
    for name in list(sys.modules):
        if name.split('.')[0] in _VENDORED:
            f = getattr(sys.modules[name], '__file__', None) or ''
            if not os.path.normcase(os.path.abspath(f)).startswith(lib):
                del sys.modules[name]
    if _LIB in sys.path:
        sys.path.remove(_LIB)
    sys.path.insert(0, _LIB)


def _drop_own_submodules():
    # ST reloads only this file; without this the mdgh modules (and their memory state)
    # would survive a package reload.
    prefix = __package__ + '.mdgh'
    for name in [n for n in sys.modules if n == prefix or n.startswith(prefix + '.')]:
        del sys.modules[name]


_use_vendored_lib()
_drop_own_submodules()

import sublime  # noqa: E402
import sublime_plugin  # noqa: E402

from .mdgh import controller  # noqa: E402


class MDGHPreviewToggleCommand(sublime_plugin.TextCommand):
    def run(self, edit, line=None):
        controller.toggle(self.view, line=line)

    def is_enabled(self, line=None):
        return controller.is_applicable(self.view)

    def is_visible(self, line=None):
        return controller.is_applicable(self.view)

    def description(self, line=None):
        return 'Edit Source' if controller.is_preview(self.view) else 'Preview'


class MDGHPreviewTabToggleCommand(sublime_plugin.WindowCommand):
    """Tab context menu: group/index name the tab that was right-clicked."""

    def _view(self, group, index):
        if group < 0 or index < 0:
            return self.window.active_view()
        sheets = self.window.sheets_in_group(group)
        return sheets[index].view() if index < len(sheets) else None

    def run(self, group=-1, index=-1):
        view = self._view(group, index)
        if view is not None and controller.is_applicable(view):
            controller.toggle(view)

    def is_visible(self, group=-1, index=-1):
        view = self._view(group, index)
        return view is not None and controller.is_applicable(view)

    def description(self, group=-1, index=-1):
        view = self._view(group, index)
        return 'Edit Source' if view is not None and controller.is_preview(view) else 'Preview'


class MDGHPreviewScrollCommand(sublime_plugin.TextCommand):
    """Preview pixel scroll; name/args are those of the move or move_to command it replaces."""

    def run(self, edit, name='move', args=None):
        controller.preview_scroll(self.view, name, args or {})


class MDGHPreviewZoomCommand(sublime_plugin.TextCommand):
    """Editor zoom keys and Ctrl+wheel: font_size and, in a target view, font_scale together."""

    def run(self, edit, step=1):
        controller.zoom(self.view, step)


class MDGHPreviewHeadingsCommand(sublime_plugin.WindowCommand):
    """Goto Symbol (@) of the active preview: its headings in a quick panel."""

    def run(self):
        controller.show_headings(self.window)


class MDGHPreviewNoopCommand(sublime_plugin.TextCommand):
    """Stands in for commands a preview view must not run."""

    def run(self, edit, hint=False):
        if hint:
            controller.show_hint(self.view)


class MDGHPreviewPanelTextCommand(sublime_plugin.TextCommand):
    """Replaces the whole text of a measurement panel."""

    def run(self, edit, text):
        self.view.replace(edit, sublime.Region(0, self.view.size()), text)


class MDGHPreviewEditSettingsCommand(sublime_plugin.WindowCommand):
    """Preferences menu. Package Control names the package after the repository, so the
    base file path is built from the installed package name rather than written out."""

    def run(self):
        self.window.run_command('edit_settings', {
            'base_file': '${packages}/%s/Markdown GitHub Preview.sublime-settings' % __package__,
            'default': '{\n\t$0\n}\n',
        })


class MDGHPreviewEvents(sublime_plugin.EventListener):
    def on_query_context(self, view, key, operator, operand, match_all):
        return controller.query_context(view, key, operator, operand, match_all)

    def on_load(self, view):
        controller.on_load(view)

    def on_activated(self, view):
        controller.on_activated(view)

    def on_deactivated(self, view):
        controller.on_deactivated(view)

    def on_pre_close(self, view):
        controller.on_pre_close(view)

    def on_post_save(self, view):
        controller.on_post_save(view)

    def on_pre_close_window(self, window):
        controller.on_pre_close_window(window)

    def on_window_command(self, window, command_name, args):
        return controller.on_window_command(window, command_name, args)


class MDGHPreviewViewEvents(sublime_plugin.ViewEventListener):
    @classmethod
    def is_applicable(cls, settings):
        return True

    @classmethod
    def applies_to_primary_view_only(cls):
        # Every clone has its own edit button.
        return False

    def on_modified(self):
        controller.on_modified(self.view)

    def on_text_command(self, command_name, args):
        return controller.on_text_command(self.view, command_name, args)

    def on_selection_modified(self):
        controller.on_selection_modified(self.view)


class MDGHPreviewBufferListener(sublime_plugin.TextChangeListener):
    """Attached by the controller to buffers that have a preview view."""

    @classmethod
    def is_applicable(cls, buffer):
        # The default would attach an instance to every buffer automatically.
        return False

    def on_text_changed(self, changes):
        controller.on_text_changed(self.buffer)

    def on_reload(self):
        controller.on_reload(self.buffer)

    def on_revert(self):
        controller.on_revert(self.buffer)


def plugin_loaded():
    controller.plugin_loaded(MDGHPreviewBufferListener)


def plugin_unloaded():
    controller.plugin_unloaded()
