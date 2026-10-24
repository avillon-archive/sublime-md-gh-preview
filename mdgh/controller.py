# -*- coding: utf-8 -*-
"""Per-view mode switching, preview drawing, recovery and update scheduling.

Everything here runs on the main thread except markdown parsing (worker).
"""
import bisect
import json
import os
import time
import webbrowser

import sublime

from . import blocks, highlight, layout, navigation, remote, render, theme
from . import input as preview_input
from .modestore import ModeStore

STATE_KEY = 'mdgh_preview.state'
BLOCK_KEY = 'mdgh_preview.block'
TOOLBAR_KEY = 'mdgh_preview.toolbar'
SPACER_KEY = 'mdgh_preview.spacer'
EDIT_BUTTON_KEY = 'mdgh_preview.edit_button'
SEL_REGIONS = 'mdgh_preview.sel'
FOLD_REGIONS = 'mdgh_preview.folds'
STATUS_KEY = 'mdgh_preview'
MSG_KEY = 'mdgh_preview.msg'   # sorts after STATUS_KEY, so the message follows 'Preview'
TOGGLE_HREF = 'mdgh:toggle'
GOTO_INPUT = 'goto_anything:input'
NOOP_COMMAND = 'mdgh_preview_noop'
HEADINGS_COMMAND = 'mdgh_preview_headings'
SCROLL_COMMAND = 'mdgh_preview_scroll'
HINT_MSG = 'Preview — Ctrl+Shift+V to edit'
MSG_MS = 3000
CLICK_S = 0.5
LOAD_WAIT_MS = 50
LOAD_WAIT_LIMIT = 400
SETTINGS_FILE = 'Markdown GitHub Preview.sublime-settings'
PREFS_FILE = 'Preferences.sublime-settings'
THEME = 'github-light'

CHUNK_S = 0.016
# Blank block phantom the viewport is held in while a position waits for its block to be drawn.
# Blocks added at the block anchor go above it; the hold breaks once more than
# half of it is drawn during one hold, far above max_file_size documents.
HOLD_SPACER_PX = 10_000_000
SPACER_HTML = '<body style="margin:0;padding:0"><div style="height: %dpx"></div></body>' % HOLD_SPACER_PX
EDIT_DEBOUNCE_MS = 150
POLL_MS = 300
GEOM_DEBOUNCE_MS = 200
SCHEME_WAIT_MS = 50
SCHEME_WAIT_LIMIT_S = 10.0
ENTER_RETRY_MS = 100
ENTER_RETRY_LIMIT = 100
IMAGE_DEBOUNCE_MS = 100

# Values a preview view runs with. color_scheme is added at entry (it depends on font size).
PREVIEW_VALUES = {
    'gutter': False, 'line_numbers': False, 'highlight_line': False, 'draw_indent_guides': False,
    'fold_buttons': False, 'spell_check': False, 'mini_diff': False, 'show_definitions': False,
    'rulers': [], 'draw_white_space': 'none', 'scroll_past_end': False, 'word_wrap': True,
    'wrap_width': 0, 'draw_centered': False, 'is_widget': True,
}
SNAPSHOT_KEYS = tuple(PREVIEW_VALUES) + ('color_scheme',)

_PLATFORM_FONTS = {
    'windows': ('Segoe UI', 'Consolas'),
    'osx': ('Helvetica Neue', 'Menlo'),
    'linux': ('DejaVu Sans', 'DejaVu Sans Mono'),
}
BUTTON_LABELS = {'preview': 'Preview', 'edit': 'Edit'}
BUTTON_TITLES = {'preview': 'Preview (Ctrl+Shift+V)', 'edit': 'Edit (Ctrl+Shift+V)'}
BUTTON_SCALE = 13.0 / 16.0
BUTTON_ICON_GAP = 0.35   # gap between icon and label, x button font px
BLOCK_PAD = 32          # GitHub markdown-body side padding at 16px body text
# A block phantom is this much narrower than viewport_extent (measured, independent of `margin`).
PHANTOM_INSET = 12

_HIDDEN_PERSISTENT = sublime.HIDDEN | sublime.PERSISTENT

# ---------------------------------------------------------------- module state

_views = {}          # view id -> _Preview
_edit_buttons = {}   # view id -> dict(pt, x, geom, pid)
_listeners = {}      # buffer id -> TextChangeListener instance
_listener_cls = None
_html_cache = {}
_HTML_CACHE_LIMIT = 20000
_schemes = {}        # scheme input key -> resource path
_ready = set()       # scheme resource paths ST has indexed
_waiting = {}        # scheme resource path -> [callbacks]
_scheme_waits = {}   # scheme resource path -> ms until ST indexed it (diagnostics)
_timeline = {'import': time.time()}   # event -> wall time of its first occurrence (diagnostics)
_debounce = {}       # (view id, kind) -> token
_pending_enter = {}  # view id -> retry count
VP_TRACE_MAX = 500
_judges = {}         # view id -> input.ClickJudge
_msg_tokens = {}     # view id -> token of the message currently shown
_alive = [False]
_store = [None]
_notes = set()
_cfg_seen = [None]     # package settings as of the last _on_settings_change
GEN_LOG_LIMIT = 32   # pv.stats['gen_log'] entries kept (diagnostics)
_settings_obj = [None]
_css_cache = [None]  # (custom_css texts, digest)
_remote = [None]     # remote.RemoteImages (created when remote_images is first on)
_block_urls = {}     # Block.html_key -> remote image URLs of that block


class _Preview:
    def __init__(self, view):
        self.view = view
        self.gen = 0
        self.doc = None
        self.starts = []
        self.ends = []
        self.keys = []           # Block.key per block (position restore)
        self.layout = None       # 'A' | 'B'
        self.anchor = 0
        self.extra = 0.0         # layout height below the last block that is not a block
        self.btn_pid = None
        self.btn_html = None
        self.toolbar_key = None  # _toolbar_key when the toolbar was drawn
        self.pids = []
        self.ys = []
        self.added = []          # html cache identity per drawn block, parallel to pids
        self.total_h = 0.0
        self.done = False
        self.ctx = None
        self.measure = None      # layout.measurer for this view's window and fonts
        self.highlight = None    # highlight(info, code) for this view's window and theme kind
        self.remote = None       # remote image lookup (None: remote_images off)
        self.geom = None
        self.pending = None      # position to apply once its block is drawn
        self.target = None       # (pending, block) resolved against the current doc
        self.top = None          # last observed top position, see _capture_top
        self.entry_vp = None
        self.stale = None        # None | 'update' | 'full': redraw owed while not visible
        self.stats = {}
        self.applying = False    # a render started and has not yet read the view's geometry
        self.spacer_pid = None   # hold spacer (SPACER_KEY) while the viewport is held in it
        self.spacer_h = 0.0      # layout height the spacer adds (0 without it)
        self.hold_y = None       # viewport y inside the spacer while holding
        self.hold_t = None       # perf_counter when the current hold started
        self.stage = None        # _Stage of an incremental update drawn below the old tail


class _Stage:
    """New block table of an incremental update whose first changed block is above the viewport.
    The new tail is added below the old one, which stays on screen, and replaces it in one
    callback once the position can be shown. Until then pv keeps the old table,
    since the old content is what is on screen."""

    def __init__(self, pv, doc, ids, start):
        self.doc = doc
        self.ids = ids
        self.starts = [b.start for b in doc.blocks]
        self.ends = [b.end for b in doc.blocks]
        self.keys = [b.key for b in doc.blocks]
        self.start = start
        # pids/ys/added: the full new table, the unchanged head copied from pv.
        self.pids = pv.pids[:start]
        self.ys = pv.ys[:start]
        self.added = pv.added[:start]
        self.target = None       # (cache key, position, block) of the position in this table


# ---------------------------------------------------------------- settings & helpers


def _cfg():
    if _settings_obj[0] is None:
        _settings_obj[0] = sublime.load_settings(SETTINGS_FILE)
    return _settings_obj[0]


def _fonts():
    s = _cfg()
    body, mono = _PLATFORM_FONTS.get(sublime.platform(), _PLATFORM_FONTS['linux'])
    return (s.get('font_body') or body), (s.get('font_mono') or mono)


def _setting_kind():
    """Kind fixed by the theme setting, or None for 'auto'."""
    want = _cfg().get('theme') or THEME
    if want not in theme.THEME_SETTINGS:
        if want not in _notes:
            _notes.add(want)
            print('Markdown GitHub Preview: unknown theme %r; drawing %s' % (want, THEME))
        want = THEME
    return theme.setting_kind(want)


def _editor_kind(view):
    """Brightness of the scheme the view shows now (valid outside the preview only)."""
    return 'dark' if theme.is_dark(view.style().get('background')) else 'light'


def _kind(view):
    """Theme kind ('light' | 'dark') the preview of this view uses."""
    k = _setting_kind()
    if k is not None:
        return k
    st = view.settings().get(STATE_KEY)
    if st and st.get('theme') in theme.KINDS:
        return st['theme']
    return _editor_kind(view)


def _judge_preview(view, st):
    """auto judgement while the view runs the preview scheme (hidden panel, see theme)."""
    w = view.window()
    if w is None:
        return st.get('theme')
    return theme.judge_kind(w, view.syntax(), (st.get('saved') or {}).get('color_scheme'))


def _rejudge(view, rerender=True):
    """Re-runs the auto judgement of a preview view; on a change stores it and redraws.
    Returns True when the kind changed."""
    st = view.settings().get(STATE_KEY) if view.is_valid() else None
    if not st or st.get('mode') != 'preview':
        return False
    k = _judge_preview(view, st)
    if k is None or k == st.get('theme'):
        return False
    st['theme'] = k
    _set_state(view, st)
    pv = _views.get(view.id())
    if rerender and pv is not None and _setting_kind() is None:
        _redraw(pv, 'theme')
    return True


def _user_css():
    """(texts, digest) of the custom_css files, read once per settings change / entry."""
    if _css_cache[0] is None:
        paths = _cfg().get('custom_css') or []
        texts, missing = theme.collect_user_css(paths, theme.load_css_file)
        for p in missing:
            # Once per file and custom_css value; a re-entry or an unrelated setting is silent.
            note = ('css', p, json.dumps(paths))
            if note not in _notes:
                _notes.add(note)
                msg = 'Markdown GitHub Preview: custom_css file not found: %s' % p
                print(msg)
                w = sublime.active_window()
                if w is not None:
                    w.status_message(msg)
        _css_cache[0] = (texts, theme.css_digest(texts))
    return _css_cache[0]


def _button_mode():
    v = _cfg().get('toggle_button', 'icon+text')
    return v if v in ('icon+text', 'text', 'none') else 'icon+text'


def _remote_lookup():
    """remote(url) for the renderer, or None when remote_images is off (no network then)."""
    if not _cfg().get('remote_images', False):
        return None
    if _remote[0] is None:
        _remote[0] = remote.RemoteImages(
            os.path.join(sublime.cache_path(), theme.PACKAGE, 'images'), _on_remote_image)
    return _remote[0].lookup


def _remote_state(b, lookup):
    """What the block's remote images resolve to now (part of its html identity), or None."""
    if lookup is None:
        return None
    urls = _block_urls.get(b.html_key)
    if urls is None:
        if len(_block_urls) > _HTML_CACHE_LIMIT:
            _block_urls.clear()
        urls = _block_urls[b.html_key] = render.remote_urls(b)
    return tuple(lookup(u) for u in urls) if urls else None


def _on_remote_image(url):
    """A remote image is cached: redraw the previews whose blocks show it, from the first
    changed block, keeping the position (the normal update path)."""
    if not _alive[0]:
        return
    for pv in list(_views.values()):
        if pv.doc is not None and any(url in _block_urls.get(b.html_key, ()) for b in pv.doc.blocks):
            _debounced(pv.view.id(), 'image', IMAGE_DEBOUNCE_MS, lambda pv=pv: _update(pv))


def _store_get():
    if not _cfg().get('remember_mode', True):
        return None
    if _store[0] is None:
        _store[0] = ModeStore(os.path.join(sublime.cache_path(), theme.PACKAGE, 'modes.json'))
    return _store[0]


def _font_scale():
    return float(_cfg().get('font_scale', 1.0) or 1.0)


def _font_size(view):
    return float(view.settings().get('font_size') or 10)


def _body_px(view):
    return theme.body_px(_font_scale())


def _button_px(view):
    # The button sits on the editor's line 1, so it follows the editor text size (pt -> px).
    return _font_size(view) * 4.0 / 3.0 * BUTTON_SCALE


def _window(view):
    return view.window() or sublime.active_window()


def _text_w(view):
    s = view.settings()
    return layout.text_area_width(view.viewport_extent()[0], view.em_width(),
                                  bool(s.get('word_wrap')), s.get('wrap_width') or 0)


def is_applicable(view):
    """Target view: a normal text view whose file extension or syntax matches the settings."""
    if view is None or not view.is_valid() or view.element() is not None:
        return False
    s = _cfg()
    name = view.file_name()
    if name:
        ext = os.path.splitext(name)[1][1:].lower()
        if ext and ext in [str(e).lower().lstrip('.') for e in s.get('file_extensions', [])]:
            return True
    sel = s.get('syntax_selector') or ''
    return bool(sel) and view.match_selector(0, sel)


def is_preview(view):
    """True while the view shows the preview (also before its first drawing finished)."""
    st = view.settings().get(STATE_KEY) if view and view.is_valid() else None
    return bool(st) and st.get('mode') == 'preview'


def _set_state(view, st):
    view.settings().set(STATE_KEY, st)


def _debounced(view_id, kind, ms, fn):
    token = _debounce.get((view_id, kind), 0) + 1
    _debounce[(view_id, kind)] = token

    def fire():
        if _alive[0] and _debounce.get((view_id, kind)) == token:
            del _debounce[(view_id, kind)]
            fn()
    sublime.set_timeout(fire, ms)


def _mix(c1, c2, t):
    def rgb(c):
        c = (c or '#808080').lstrip('#')
        return [int(c[i:i + 2], 16) for i in (0, 2, 4)] if len(c) >= 6 else [128, 128, 128]
    a, b = rgb(c1), rgb(c2)
    return '#%02x%02x%02x' % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


# ---------------------------------------------------------------- color scheme


def _scheme_key(kind, bpx):
    body_face, mono_face = _fonts()
    return (theme.theme_name(kind), body_face, mono_face, round(bpx, 3), _user_css()[1])


def _scheme_input(view):
    return _scheme_key(_kind(view), _body_px(view))


def _scheme_path(view):
    """Resource path of the preview scheme for this view (written on first use)."""
    return _scheme_for(_scheme_input(view), _window(view))


def _scheme_for(key, window):
    path = _schemes.get(key)
    if path is not None and not os.path.exists(_scheme_file(path)):
        # Pruned or deleted by hand: write it again and wait for ST to index it again.
        _ready.discard(path)
        path = None
    if path is None:
        name, body_face, mono_face, bpx, _digest = key
        vars, base = theme.load_theme(name)
        h_body = layout.line_height(window, 'body', layout.css_font(body_face, bpx))
        h_mono = layout.line_height(window, 'mono',
                                    layout.css_font(mono_face, theme.pre_px(vars, bpx)))
        css = theme.build_css(vars, base, body_px=bpx, font_body=body_face, font_mono=mono_face,
                              h_body=h_body, h_mono=h_mono, user_css=_user_css()[0])
        path = theme.write_scheme(name, theme.build_scheme(vars, css))
        _schemes[key] = path
    _touch_scheme(path)
    return path


def _scheme_file(path):
    return os.path.join(theme.scheme_dir(), path.rsplit('/', 1)[-1])


def _touch_scheme(path):
    # The mtime is the recency theme.prune_schemes keeps by.
    try:
        os.utime(_scheme_file(path))
    except FileNotFoundError:
        pass


def _theme_vars(kind):
    return theme.load_theme(theme.theme_name(kind))[0]


def _when_ready(path, fn):
    """Runs fn once ST indexed the scheme file at path."""
    if path in _ready:
        fn()
        return
    if path in _waiting:
        _waiting[path].append(fn)
        return
    _waiting[path] = [fn]
    t0 = time.perf_counter()

    def check():
        if not _alive[0]:
            return
        if theme.scheme_ready(path):
            _ready.add(path)
            _scheme_waits[path] = round((time.perf_counter() - t0) * 1000, 1)
            for cb in _waiting.pop(path, []):
                cb()
            return
        if time.perf_counter() - t0 > SCHEME_WAIT_LIMIT_S:
            _waiting.pop(path, None)
            for pv in _views.values():
                pv.applying = False   # renders waiting here were dropped; let geometry polling retry
            print('Markdown GitHub Preview: color scheme %s was not picked up by Sublime Text' % path)
            return
        sublime.set_timeout(check, SCHEME_WAIT_MS)
    check()


def _prune_schemes():
    keep = set(_waiting)
    for w in sublime.windows():
        for v in w.views():
            cs = v.settings().get('color_scheme')
            if cs:
                keep.add(cs)
    keep.update(_premade_paths())
    removed = set(theme.prune_schemes(keep))
    for key, path in list(_schemes.items()):
        if path.rsplit('/', 1)[-1] in removed:
            del _schemes[key]
            _ready.discard(path)


def _zoom_file():
    return os.path.join(sublime.cache_path(), theme.PACKAGE, 'zoom.json')


def _zoom_anchor():
    try:
        with open(_zoom_file(), encoding='utf-8') as f:
            return tuple(json.load(f))
    except (OSError, ValueError, TypeError):   # none yet: the step starts one
        return None


def _zoom_scales(old):
    """font_scale of the current font_size and of the steps one zoom away from it."""
    anchor, scale = _zoom_anchor(), _font_scale()
    scales = [scale]
    for new in (old - 1, old + 1):
        if new >= 1:
            scales.append(theme.zoom_scale(anchor, scale, old, new)[1])
    return scales


def _premade_keys():
    """Schemes for the current font_scale and its zoom neighbours in every kind the theme
    setting can pick."""
    old = sublime.load_settings(PREFS_FILE).get('font_size') or 10
    k = _setting_kind()
    return [_scheme_key(kind, theme.body_px(scale))
            for scale in _zoom_scales(old) for kind in ((k,) if k else theme.KINDS)]


def _premade_paths():
    """Premade schemes, kept by pruning so the next entry need not wait."""
    return [_schemes[key] for key in _premade_keys() if key in _schemes]


def _premake():
    """Writes the schemes for the current font_scale and its zoom neighbours so entering or
    zooming need not wait."""
    w = sublime.active_window()
    if w is None:
        return
    for key in _premade_keys():
        _when_ready(_scheme_for(key, w), lambda: None)


# ---------------------------------------------------------------- buttons


def _button_font(view):
    return layout.css_font(_fonts()[0], _button_px(view))


def _button_icon(view):
    """(icon display px, gap px after it); (0, 0) without an icon."""
    if _button_mode() != 'icon+text':
        return 0, 0
    px = _button_px(view)
    return int(round(px)), int(round(px * BUTTON_ICON_GAP))


def _button_width(view):
    """Common width of both buttons so the button keeps its place when the mode flips."""
    if _button_mode() == 'none':
        return 0.0
    ws = layout.widths(_window(view), 'body', _button_font(view), list(BUTTON_LABELS.values()))
    icon, gap = _button_icon(view)
    return float(max(ws)) + icon + gap


def _button_html(view, mode, pad, color, kind):
    """kind: 'light' | 'dark' icon set, chosen by the background the button is drawn on."""
    body_face = _fonts()[0]
    px = _button_px(view)
    label = BUTTON_LABELS[mode]
    w = _button_width(view)
    lw = layout.widths(_window(view), 'body', _button_font(view), [label])[0]
    icon, gap = _button_icon(view)
    img = ''
    if icon:
        # padding on <img> is ignored by minihtml (measured); the label span carries the gap.
        img = '%s<span style="padding-left: %dpx">' % (theme.icon_html(mode, kind, icon), gap)
    # The <style> lives in this phantom (not phantom_css) because in edit mode the view runs
    # the user's color scheme, and the button must look the same in both modes.
    return ('<body id="mdgh-btn"><style>html, body {{ margin: 0; padding: 0; }} '
            'a {{ color: {c}; text-decoration: none; font-family: "{f}"; font-size: {px:.2f}px; }}'
            '</style><span style="padding-left: {pl}px; padding-right: {pr}px">'
            '<a href="{href}" title="{title}">{img}{label}{img_end}</a></span></body>'
            ).format(c=color, f=body_face.replace('"', ''), px=px, pl=int(pad),
                     pr=max(0, int(round(w - lw - icon - gap))), href=TOGGLE_HREF,
                     title=BUTTON_TITLES[mode], img=img, label=label,
                     img_end='</span>' if img else '')


def _line1_end(view):
    """(end point of line 1, its last character and that character's layout position). The x
    of the end point itself is not used: with the button phantom there, text_to_layout can
    report the x after the button (a view just opened in a new window), and
    comparing it with the x measured before the button was added moves the button every poll."""
    line0 = view.line(0)
    if line0.empty():
        return (line0.b, '', None)
    return (line0.b, view.substr(line0.b - 1), tuple(view.text_to_layout(line0.b - 1)))


def _edit_geom(view):
    style = view.style()
    return (_line1_end(view), _text_w(view), _font_size(view), view.settings().get('font_face'),
            _button_mode(), _cfg().get('font_scale', 1.0), style.get('background'),
            style.get('foreground'))


def place_edit_button(view):
    """(Re)draws the edit-mode button at the end of line 1, or removes it when not wanted."""
    vid = view.id()
    if not _alive[0] or not view.is_valid():
        return
    if is_preview(view) or not is_applicable(view) or _button_mode() == 'none':
        remove_edit_button(view)
        return
    if view.viewport_extent()[0] <= 0:
        return
    geom = _edit_geom(view)
    old = _edit_buttons.get(vid)
    if old and old['geom'] == geom and view.query_phantom(old['pid']):
        return
    pt, text_w = geom[0][0], geom[1]
    # The end of line 1 is measured without the button (see _line1_end).
    view.erase_phantoms(EDIT_BUTTON_KEY)
    pad, _wraps = layout.edit_button_pad(text_w, view.text_to_layout(pt)[0], _button_width(view))
    style = view.style()
    color = _mix(style.get('foreground'), style.get('background'), 0.45)
    html = _button_html(view, 'preview', pad, color, _editor_kind(view))
    pid = view.add_phantom(EDIT_BUTTON_KEY, sublime.Region(pt), html, sublime.LAYOUT_INLINE,
                           on_navigate=lambda href, vid=vid: _navigate(vid, href))
    _edit_buttons[vid] = {'html': html, 'geom': geom, 'pid': pid}


def remove_edit_button(view):
    if _edit_buttons.pop(view.id(), None) is not None or view.is_valid():
        view.erase_phantoms(EDIT_BUTTON_KEY)


def on_modified(view):
    """Edit mode: typing at the end of line 1 leaves the inline phantom at the old point, so the
    button is moved in the same callback."""
    info = _edit_buttons.get(view.id())
    if info is None or is_preview(view):
        return
    if _line1_end(view) != info['geom'][0]:
        place_edit_button(view)


# ---------------------------------------------------------------- toolbar & layout


def _editor_font(view):
    s = view.settings()
    return {'font_face': s.get('font_face') or '', 'font_size': _font_size(view),
            'tab_size': s.get('tab_size') or 4}


def _toolbar_layout(view, size):
    """'A' | 'B'. Line 1 is measured in the width panel, so phantoms in the view do not count."""
    if size == 0:
        return 'A'
    line1 = view.substr(view.line(0))
    w1 = layout.widths(_window(view), 'editor', _editor_font(view), [line1])[0] if line1 else 0.0
    return layout.choose_layout(w1, _text_w(view), _button_width(view))


def _toolbar_key(view, kind):
    """What the toolbar button depends on besides the render context and geometry (compared
    separately): the redraw keeps the button while this is unchanged. Not the x of the end of
    line 1: with the button phantom there, text_to_layout can report the x after the button."""
    line0 = view.line(0)
    text = view.substr(line0) if kind == 'A' else view.substr(sublime.Region(0, min(1, line0.b)))
    return (kind, line0.b if kind == 'A' else 0, text, _editor_font(view), _button_mode())


def _toolbar(pv, size):
    """Chooses layout A/B, folds the source accordingly and returns the toolbar button html.
    Measures the end of line 1, so the toolbar phantom must not be in the view."""
    view = pv.view
    line0 = view.line(0)
    text_w = _text_w(view)
    bw = _button_width(view)
    kind = _toolbar_layout(view, size)
    anchor = line0.b if kind == 'A' else 0
    _fold(view, kind, size, line0.b)
    html = None
    if _button_mode() != 'none':
        if kind == 'A':
            # Same place as the edit-mode button: the end of line 1.
            pad = layout.edit_button_pad(text_w, view.text_to_layout(line0.b)[0], bw)[0]
        else:
            first_w = view.text_to_layout(1)[0] - view.text_to_layout(0)[0]
            pad = layout.toolbar_b_pad(text_w, bw, first_w, _marker_w(view))
        tk = _kind(view)
        html = _button_html(view, 'edit', pad, _theme_vars(tk)['colors']['muted'], tk)
    return kind, anchor, html


def _marker_w(view):
    return 3.0 * view.em_width()


def _fold(view, kind, size, anchor_line_end):
    span = layout.fold_span(kind, size, anchor_line_end)
    want = [sublime.Region(*span)] if span else []
    have = view.folded_regions()
    if [(r.a, r.b) for r in have] == [(r.a, r.b) for r in want]:
        return
    if have:
        view.unfold(sublime.Region(0, size))
    for r in want:
        view.fold(r)


def _anchor_now(pv):
    pid = pv.btn_pid if pv.btn_pid is not None else (pv.pids[0] if pv.pids else None)
    if pid is not None:
        regs = pv.view.query_phantom(pid)
        if regs and regs[0].a >= 0:
            return regs[0].a
    return pv.anchor


def _refold(pv):
    """Re-grabs the fold after a buffer change: text appended at the end or inserted before
    the fold start would otherwise show."""
    view = pv.view
    size = view.size()
    if pv.layout is None:
        return
    if pv.layout == 'B':
        _fold(view, 'B', size, 0)
    else:
        a = min(_anchor_now(pv), size)
        _fold(view, 'A', size, view.line(a).b)


# ---------------------------------------------------------------- rendering


def _ctx(view):
    bpx = _body_px(view)
    try:
        max_w = max(0.0, float(_cfg().get('content_max_width', 980) or 0))
    except (TypeError, ValueError):
        max_w = 980.0
    pl, pr, avail = render.block_pads(_text_w(view) - PHANTOM_INSET,
                                      int(round(BLOCK_PAD * bpx / 16.0)), max_w * bpx / 16.0)
    kind = _kind(view)
    path = view.file_name()
    return render.RenderContext(body_px=bpx, pad_left=pl, pad_right=pr, theme=kind, avail=avail,
                                metrics=theme.layout_metrics(_theme_vars(kind), bpx),
                                fonts=_fonts(), doc_dir=os.path.dirname(path) if path else '')


def _measure(view):
    return layout.measurer(_window(view), *_fonts())


def _highlighter(view, kind):
    window = _window(view)
    return lambda info, code: highlight.lines(window, kind, info, code)


def _geom(view):
    return (_text_w(view), _font_size(view))


def _html_for(doc, k, ctx, measure, hl, lookup=None):
    if k < 0:
        key = ('empty', ctx.key())
    else:
        b = doc.blocks[k]
        key = (b.html_key, b.index == 0, ctx.key(), _remote_state(b, lookup))
    h = _html_cache.get(key)
    if h is None:
        if len(_html_cache) > _HTML_CACHE_LIMIT:
            _html_cache.clear()
        h = (render.render_empty(ctx) if k < 0
             else render.render_block(doc.blocks[k], doc, ctx, measure, hl, remote=lookup))
        _html_cache[key] = h
    return h


def _identities(doc, lookup=None):
    if not doc.blocks:
        return [('empty',)]
    return [(b.html_key, b.index == 0, _remote_state(b, lookup)) for b in doc.blocks]


def _start_render(pv, full=False, pos=None, reason=''):
    pv.gen += 1
    g = pv.gen
    pv.applying = True
    view = pv.view
    log = pv.stats.setdefault('gen_log', [])
    log.append((g, reason, round(time.perf_counter(), 4), pv.geom, _geom(view),
                _scheme_path(view) not in _ready))
    del log[:-GEN_LOG_LIMIT]
    if full or pv.stale == 'update':
        pv.stale = None   # this render reads the current text; an owed 'full' outlives a partial one
    text = view.substr(sublime.Region(0, view.size()))
    t0 = time.perf_counter()
    if pos is not None:
        pv.pending = pos

    def work():
        doc = blocks.parse(text)
        t1 = time.perf_counter()
        sublime.set_timeout(lambda: _apply(pv, g, doc, full, reason, t0, t1), 0)
    sublime.set_timeout_async(work, 0)


def _alive_pv(pv, g):
    return (_alive[0] and pv.gen == g and _views.get(pv.view.id()) is pv and pv.view.is_valid())


def _apply(pv, g, doc, full, reason, t0, t1):
    if not _alive_pv(pv, g):
        return
    view = pv.view
    path = _scheme_path(view)
    if path not in _ready:
        _when_ready(path, lambda: _apply(pv, g, doc, full, reason, t0, t1))
        return
    s = view.settings()
    if s.get('color_scheme') != path:
        s.set('color_scheme', path)
        _touch_scheme(path)
        full = True
        sublime.set_timeout(_prune_schemes, 1000)
    t2 = time.perf_counter()
    if pv.stage is not None:
        # Not committed: the old table is still the one drawn, this render judges from it.
        _stage_drop(pv)
    ctx = _ctx(view)
    geom = _geom(view)
    pv.applying = False
    size = view.size()
    lookup = _remote_lookup()
    ids = _identities(doc, lookup)
    if (not full and pv.doc is not None and pv.ctx == ctx and pv.geom == geom
            and pv.layout is not None):
        # Same toolbar? Line 1 edits change the button padding or move the anchor.
        key = _toolbar_key(view, _toolbar_layout(view, size))
        if key != pv.toolbar_key or key[1] != _anchor_now(pv):
            full = True
    else:
        full = True
    if full:
        view.erase_phantoms(BLOCK_KEY)
        view.erase_phantoms(TOOLBAR_KEY)
        pv.pids, pv.ys, pv.added = [], [], []
        pv.btn_pid = None
        kind, anchor, html = _toolbar(pv, size)
        pv.layout, pv.anchor, pv.btn_html = kind, anchor, html
        pv.toolbar_key = _toolbar_key(view, kind)
        # The button must be added before the blocks and at the same point, otherwise it is
        # not drawn on the toolbar line.
        if html is not None:
            pv.btn_pid = view.add_phantom(TOOLBAR_KEY, sublime.Region(anchor), html,
                                          sublime.LAYOUT_INLINE,
                                          on_navigate=lambda href, vid=view.id(): _navigate(vid, href))
        line1_bottom = view.text_to_layout(0)[1] + view.line_height()
        # The hold spacer outlives the erase above (other key) and is not content below blocks.
        pv.extra = view.layout_extent()[1] - line1_bottom - pv.spacer_h
        start = 0
    else:
        start = layout.first_diff(pv.added, ids)
        if (pv.done and start < len(pv.ys) and not _holding(pv)
                and pv.ys[start] < view.viewport_position()[1]):
            # Erasing the tail would show the content above the viewport until the position
            # is drawn again; the old tail stays on screen instead.
            pv.stage = _Stage(pv, doc, ids, start)
        else:
            for pid in pv.pids[start:]:
                view.erase_phantom_by_id(pid)
            del pv.pids[start:], pv.ys[start:], pv.added[start:]
    if pv.stage is None:
        pv.doc = doc
        pv.ids = ids
        pv.starts = [b.start for b in doc.blocks]
        pv.ends = [b.end for b in doc.blocks]
        pv.keys = [b.key for b in doc.blocks]
        pv.done = False
        pv.target = None
        if pv.pending is not None and pv.pending[0] != 'y':
            _pending_block(pv)
    pv.ctx = ctx
    pv.measure = _measure(view)
    pv.highlight = _highlighter(view, ctx.theme)
    pv.remote = lookup
    pv.geom = geom
    st = pv.stats
    # done_ms too: a staged render keeps pv.done (the old table is complete) until it finishes.
    for key in ('pos_ms', 'edit_visible_ms', 'hold_start_ms', 'done_ms'):
        st.pop(key, None)
    st['vp_trace'] = []
    st['gen_t0'] = t0
    if _holding(pv) and pv.hold_t >= t0:
        # Started by on_reload, before this render's stats existed.
        st['hold_start_ms'] = round((pv.hold_t - t0) * 1000, 1)
        st['vp_trace'].append([st['hold_start_ms'], pv.hold_y, 1])
    st.update(reason=reason, parse_ms=round((t1 - t0) * 1000, 1), full=full, start=start,
              blocks=len(doc.blocks), chunks=0, max_chunk_ms=0.0, chunk_ms=0.0, prep_ms=0.0,
              staged=pv.stage is not None)
    st['prep_ms'] = round((time.perf_counter() - t2) * 1000, 1)
    _chunk(pv, g, t0)


def _chunk(pv, g, t0):
    if not _alive_pv(pv, g):
        return
    view = pv.view
    c0 = time.perf_counter()
    deadline = c0 + CHUNK_S
    tgt = pv.stage or pv     # the table blocks are added to: the stage until it is committed
    doc = tgt.doc
    n = len(tgt.ids)
    k = len(tgt.pids)
    anchor = sublime.Region(pv.anchor)
    nav = (lambda href, vid=view.id(): _navigate(vid, href))
    while k < n:
        html = _html_for(doc, k if doc.blocks else -1, pv.ctx, pv.measure, pv.highlight,
                         pv.remote)
        y = _drawn_h(pv)
        if tgt is not pv:
            y = navigation.staged_y(y, pv.ys, pv.total_h, tgt.start)
        pid = view.add_phantom(BLOCK_KEY, anchor, html, sublime.LAYOUT_BLOCK, on_navigate=nav)
        tgt.pids.append(pid)
        tgt.ys.append(y)
        if k == pv.stats['start'] and not pv.stats['full'] and tgt is pv:
            pv.stats['edit_visible_ms'] = round((time.perf_counter() - t0) * 1000, 1)
        tgt.added.append(tgt.ids[k])
        k += 1
        if tgt is not pv:
            if _stage_try_commit(pv):
                tgt = pv
        elif pv.pending is not None:
            _try_position(pv)
        if time.perf_counter() >= deadline:
            break
    st = pv.stats
    dt = (time.perf_counter() - c0) * 1000
    st['chunks'] = st.get('chunks', 0) + 1
    st['max_chunk_ms'] = round(max(st.get('max_chunk_ms', 0.0), dt), 2)
    st['chunk_ms'] = round(st.get('chunk_ms', 0.0) + dt, 2)
    if k < n:
        if pv.stage is None and pv.pending is not None and not _holding(pv):
            # A render's first chunk runs in the callback that erased the blocks, so no frame
            # shows the content above the position before the hold starts.
            _hold_start(pv, t0)
        else:
            _trace_viewport(pv, t0)
        sublime.set_timeout(lambda: _chunk(pv, g, t0), 0)
        return
    if pv.stage is not None:
        # No new block was left to add (the update only removed blocks at the end).
        _stage_try_commit(pv)
    pv.total_h = _drawn_h(pv)
    pv.done = True
    if pv.pending is not None:
        _try_position(pv)
    _trace_viewport(pv, t0)
    st['done_ms'] = round((time.perf_counter() - t0) * 1000, 1)
    if 'reload_t0' in st:
        st['reload_ms'] = round((time.perf_counter() - st.pop('reload_t0')) * 1000, 1)
    _capture_top(pv)


def _trace_viewport(pv, t0, y=None):
    # Diagnostics: [ms, viewport y, 1 while holding else 0] after each chunk and at the start and
    # end of a hold, capped so a long render stays bounded.
    trace = pv.stats.setdefault('vp_trace', [])
    if len(trace) < VP_TRACE_MAX:
        trace.append([round((time.perf_counter() - t0) * 1000, 1),
                      pv.view.viewport_position()[1] if y is None else y, 1 if _holding(pv) else 0])


# ---------------------------------------------------------------- hold and stage


def _drawn_h(pv):
    """Bottom of the drawn blocks: the layout height without what is not a block."""
    return pv.view.layout_extent()[1] - pv.extra - pv.spacer_h


def _holding(pv):
    return pv.spacer_pid is not None


def _hold_start(pv, t0=None):
    """Holds the viewport in a blank spacer below the drawn content until the pending position
    can be shown (with scroll_past_end off ST would otherwise clamp the viewport to the drawn
    content, showing the top of the document). t0: the render whose stats record the start
    (None: the next render's _apply records it)."""
    view = pv.view
    y = _drawn_h(pv) + HOLD_SPACER_PX / 2
    _add_spacer(pv)
    pv.hold_y = y
    pv.hold_t = time.perf_counter()
    _scroll(view, y)
    if t0 is not None:
        pv.stats['hold_start_ms'] = round((pv.hold_t - t0) * 1000, 1)
        _trace_viewport(pv, t0, y)


def _add_spacer(pv):
    view = pv.view
    e0 = view.layout_extent()[1]
    pv.spacer_pid = view.add_phantom(SPACER_KEY, sublime.Region(view.size()), SPACER_HTML,
                                     sublime.LAYOUT_BLOCK)
    pv.spacer_h = view.layout_extent()[1] - e0


def _hold_reanchor(pv):
    """Moves the spacer to the new end after a buffer change: text appended at the end leaves
    its anchor at the old end, inside the fold that is grabbed again up to the new end."""
    pv.view.erase_phantom_by_id(pv.spacer_pid)
    _add_spacer(pv)
    _scroll(pv.view, pv.hold_y)


def _hold_end(pv):
    """Ends a hold; the caller has already set the viewport (same callback, so no frame shows
    the clamped viewport)."""
    if pv.spacer_pid is None:
        return
    pv.view.erase_phantom_by_id(pv.spacer_pid)
    pv.spacer_pid, pv.spacer_h, pv.hold_y = None, 0.0, None
    t0 = pv.stats.get('gen_t0')
    if t0 is not None:
        _trace_viewport(pv, t0)


def _hold_resume(pv, p):
    """Puts back pending position p after a user action that started at a hold was cancelled."""
    pv.pending = p
    if pv.done:
        _try_position(pv)
    elif not _holding(pv):
        _hold_start(pv, pv.stats.get('gen_t0'))


def _stage_drop(pv):
    stage, pv.stage = pv.stage, None
    for pid in stage.pids[stage.start:]:
        pv.view.erase_phantom_by_id(pid)


def _stage_position(pv, stage):
    """(position, its block in the staged table). The pending position, or when the user moved
    since (scroll_to clears it), their top in the old table that is still on screen."""
    p = pv.pending
    c = stage.target
    if p is None:
        key = ('top', pv.view.viewport_position()[1])
        if c is not None and c[0] == key:
            return c[1], c[2]
        p = _capture_top(pv)
    else:
        key = p
        if c is not None and c[0] is p:
            return c[1], c[2]
    k = _block_for(p, stage.doc, stage.starts, stage.keys) if p[0] != 'y' and stage.starts else None
    stage.target = (key, p, k)
    return p, k


def _stage_try_commit(pv):
    """Replaces the old tail by the staged one when the position can be shown in the new table:
    old tail erased, table swapped and viewport set in this one callback. Returns True then."""
    stage = pv.stage
    view = pv.view
    all_drawn = len(stage.pids) == len(stage.ids)
    p, k = _stage_position(pv, stage)
    # The layout is queried only once the position's block is drawn (one query per added block
    # otherwise).
    drawn_h = navigation.staged_y(_drawn_h(pv), pv.ys, pv.total_h, stage.start) if all_drawn else None
    y = navigation.target_y(p, stage.starts, stage.ends, stage.ys, drawn_h, k)
    if y is None:
        return False
    if drawn_h is None:
        drawn_h = navigation.staged_y(_drawn_h(pv), pv.ys, pv.total_h, stage.start)
    if not navigation.can_show(y, all_drawn, drawn_h, view.viewport_extent()[1]):
        return False
    for pid in pv.pids[stage.start:]:
        view.erase_phantom_by_id(pid)
    pv.pids, pv.ys, pv.added = stage.pids, stage.ys, stage.added
    pv.doc, pv.ids = stage.doc, stage.ids
    pv.starts, pv.ends, pv.keys = stage.starts, stage.ends, stage.keys
    pv.done = False
    pv.target = None
    pv.stage = None
    t0 = pv.stats.get('gen_t0')
    if t0 is not None:
        pv.stats['edit_visible_ms'] = round((time.perf_counter() - t0) * 1000, 1)
    _set_position(pv, y)
    return True


# ---------------------------------------------------------------- positions


def _h_of(pv, k):
    if k + 1 < len(pv.ys):
        return pv.ys[k + 1] - pv.ys[k]
    if pv.done and k == len(pv.ys) - 1:
        return pv.total_h - pv.ys[k]
    return None


def _drawn_table(pv, k):
    """Partial (starts, ends, ys, total_h) that is exact for blocks 0..k (needs k+1 drawn)."""
    m = k + 1
    total = pv.ys[m] if m < len(pv.ys) else pv.total_h
    return pv.starts[:m], pv.ends[:m], pv.ys[:m], total


def _pending_block(pv):
    """Block of pv.pending in pv.doc, resolved once per (pending, doc): _apply clears the
    cache for a new doc and a replaced pending tuple misses it."""
    p = pv.pending
    t = pv.target
    if t is not None and t[0] is p:
        return t[1]
    k = _block_for(p, pv.doc, pv.starts, pv.keys)
    pv.target = (p, k)
    return k


def _block_for(p, doc, starts, keys):
    frag = _fragment_index(doc, p[1]) if p[0] == 'slug' else None
    return navigation.pending_block(p, starts, keys, frag)


def _try_position(pv):
    p = pv.pending
    if p[0] != 'y' and pv.doc is None:
        return
    k = _pending_block(pv) if p[0] != 'y' and pv.starts else None
    y = navigation.target_y(p, pv.starts, pv.ends, pv.ys, pv.total_h if pv.done else None, k)
    if y is not None and navigation.can_show(y, pv.done, _drawn_h(pv),
                                             pv.view.viewport_extent()[1]):
        _set_position(pv, y)


def _set_position(pv, y):
    """Applies the pending position at y and ends a hold."""
    pv.pending = None
    t0 = pv.stats.get('gen_t0')
    if t0 is not None:
        pv.stats['pos_ms'] = round((time.perf_counter() - t0) * 1000, 1)
    _scroll(pv.view, max(0.0, y))
    _hold_end(pv)
    pv.entry_vp = pv.view.viewport_position()


def _scroll(view, y):
    view.set_viewport_position((0.0, y), False)


def _capture_top(pv):
    """Remembers the block at the top of the viewport and the offset inside it."""
    if not pv.done or not pv.ys:
        return pv.top
    vy = pv.view.viewport_position()[1]
    if vy < pv.ys[0]:
        top = ('y', vy)
    else:
        k = max(0, bisect.bisect_right(pv.ys, vy) - 1)
        h = _h_of(pv, k) or 0.0
        frac = min(max((vy - pv.ys[k]) / h, 0.0), 1.0) if h > 0 else 0.0
        top = ('keys', list(pv.keys), k, frac)
    pv.top = top
    return top


def _top_basis(pv):
    """(y, pending source line) the top position is judged from. While drawing, a pending
    position wins over the viewport ST clamped to the drawn content."""
    vy = pv.view.viewport_position()[1]
    pl = None
    p = None if pv.done else pv.pending
    if p is not None:
        if p[0] == 'y':
            vy = p[1]
        else:
            pl = navigation.pending_line(p, pv.starts, pv.ends, _pending_block(pv))
    return vy, pl


def _top_line(pv):
    if pv is None or not pv.starts:
        return 0
    vy, pl = _top_basis(pv)
    if not pv.done:
        return navigation.drawing_top_line(pv.starts, pv.ends, pv.ys, _drawn_h(pv), vy, pl)
    if vy < pv.ys[0]:
        return 0
    return navigation.y_to_line(pv.starts, pv.ends, pv.ys, pv.total_h, vy)


def _persist_top(pv):
    """Copies the top position into the view state (survives restart) when it changed."""
    top = _capture_top(pv)
    if top is None:
        return
    st = pv.view.settings().get(STATE_KEY)
    if not st or st.get('mode') != 'preview':
        return
    if top[0] == 'y':
        rec = {'y': top[1], 'line': 0}
    else:
        k = top[2]
        rec = {'index': k, 'key': top[1][k] if k < len(top[1]) else None, 'frac': top[3],
               'line': _top_line(pv)}
    if st.get('top') != rec:
        st['top'] = rec
        _set_state(pv.view, st)


def _pos_from_record(rec):
    if not rec:
        return ('y', 0.0)
    if 'y' in rec:
        return ('y', float(rec['y']))
    k = int(rec.get('index', 0))
    if rec.get('key'):
        return ('keys', [''] * k + [rec['key']], k, float(rec.get('frac', 0.0)))
    return ('block', int(rec.get('line', 0)))


# ---------------------------------------------------------------- enter / exit


def _base_line(view):
    """Edit-mode reference row: the main caret's row when on screen, else the top row."""
    vr = view.visible_region()
    sel = view.sel()
    vy = view.viewport_position()[1]
    if len(sel) and vr.contains(sel[0].b):
        row = view.rowcol(sel[0].b)[0]
    else:
        row = view.rowcol(vr.a)[0]
        if view.text_to_layout(view.text_point(row, 0))[1] < vy and row + 1 < view.rowcol(view.size())[0] + 1:
            row += 1
    screen_y = view.text_to_layout(view.text_point(row, 0))[1] - vy
    return row, screen_y, vy <= 0


def _too_big(view):
    limit = int(_cfg().get('max_file_size', 300000) or 0)
    if limit <= 0:
        return False
    n = view.size()
    if n * 4 <= limit:
        return False
    if n > limit:
        return True
    return len(view.substr(sublime.Region(0, n)).encode('utf-8')) > limit


def enter(view, line=None, screen_y=None, pos=None):
    """Switches view to the preview. line/screen_y: put that row at that screen height;
    pos: explicit position record (internal). Returns False when it did not start."""
    if not _alive[0] or not is_applicable(view) or is_preview(view):
        return False
    vid = view.id()
    if _too_big(view):
        w = view.window()
        if w:
            w.status_message('Markdown GitHub Preview: file is larger than max_file_size; preview is off')
        return False
    if view.is_loading() or view.viewport_extent()[0] <= 0:
        _defer_enter(view, line, screen_y, pos)
        return False
    _pending_enter.pop(vid, None)
    t_enter = time.perf_counter()
    _css_cache[0] = None     # custom_css is read again at every entry
    # auto judgement: the view still runs the editor scheme here.
    entry_kind = _editor_kind(view)
    path = _scheme_path(view)
    if path not in _ready:
        _pending_enter[vid] = 0

        def go():
            if _pending_enter.pop(vid, None) is not None and view.is_valid():
                enter(view, line, screen_y, pos)
        _when_ready(path, go)
        return True
    if pos is None:
        if line is None:
            row, sy, at_top = _base_line(view)
        else:
            row, sy, at_top = int(line), float(screen_y or 0.0), False
        pos = ('line', row, sy, at_top)
    s = view.settings()
    saved = {}
    for k in SNAPSHOT_KEYS:
        # Same callback: the value read right after erase is the inherited one, so a change
        # means a view-level value existed. Settings.has/in/to_dict see inherited values too.
        v1 = s.get(k)
        s.erase(k)
        v2 = s.get(k)
        if v1 != v2:
            saved[k] = v1
    vx, vy = view.viewport_position()
    top_pt = view.layout_to_text((vx, vy))
    st = {'mode': 'preview', 'saved': saved, 'theme': entry_kind, 'vp': [vx, vy],
          'vp_pt': top_pt, 'vp_off': vy - view.text_to_layout(top_pt)[1],
          'cc': view.change_count(), 'reloaded': False}
    view.add_regions(SEL_REGIONS, list(view.sel()), flags=_HIDDEN_PERSISTENT)
    view.add_regions(FOLD_REGIONS, view.folded_regions(), flags=_HIDDEN_PERSISTENT)
    remove_edit_button(view)
    for k, v in PREVIEW_VALUES.items():
        s.set(k, v)
    s.set('color_scheme', path)
    _touch_scheme(path)
    _set_state(view, st)
    view.unfold(sublime.Region(0, view.size()))
    view.sel().clear()
    view.set_status(STATUS_KEY, 'Preview')
    pv = _Preview(view)
    pv.stats['enter_t0'] = t_enter
    _views[vid] = pv
    _attach(view)
    if pos[0] in ('line', 'block', 'slug') or (pos[0] == 'y' and pos[1] == 0):
        _scroll(view, 0.0)
    _start_render(pv, full=True, pos=pos, reason='enter')
    store = _store_get()
    if store is not None and view.file_name():
        store.put(view.file_name(), pos[1] if pos[0] in ('line', 'block') else 0)
    return True


def _defer_enter(view, line, screen_y, pos):
    vid = view.id()
    n = _pending_enter.get(vid, 0)
    if n >= ENTER_RETRY_LIMIT:
        _pending_enter.pop(vid, None)
        return
    _pending_enter[vid] = n + 1

    def retry():
        if _pending_enter.get(vid) == n + 1 and view.is_valid() and not is_preview(view):
            if not view.is_loading() and view.viewport_extent()[0] > 0:
                _pending_enter.pop(vid, None)
            enter(view, line, screen_y, pos)
    sublime.set_timeout(retry, ENTER_RETRY_MS)


def _restore_view_state(view, st):
    """Undoes everything entry changed on the view, from the stored state alone."""
    s = view.settings()
    view.erase_phantoms(BLOCK_KEY)
    view.erase_phantoms(TOOLBAR_KEY)
    view.erase_phantoms(SPACER_KEY)
    view.unfold(sublime.Region(0, view.size()))
    for k in SNAPSHOT_KEYS:
        s.erase(k)
    for k, v in (st.get('saved') or {}).items():
        s.set(k, v)
    if not st.get('reloaded'):
        # A reload does not move regions, so after one the stored folds are stale.
        for r in view.get_regions(FOLD_REGIONS):
            if not r.empty():
                view.fold(r)
    sel = [] if st.get('reloaded') else view.get_regions(SEL_REGIONS)
    view.erase_regions(FOLD_REGIONS)
    view.erase_regions(SEL_REGIONS)
    s.erase(STATE_KEY)
    view.erase_status(STATUS_KEY)
    return sel


def exit(view, line=None, screen_y=None):
    """Switches view back to the source. line/screen_y: put that row at that screen height and
    the caret at its start. Returns False when the view was not in the preview."""
    st = view.settings().get(STATE_KEY)
    if not st or st.get('mode') != 'preview':
        return False
    vid = view.id()
    pv = _views.pop(vid, None)
    _pending_enter.pop(vid, None)
    view.erase_status(MSG_KEY)
    given = line is not None
    unchanged = False
    if pv is not None:
        pv.gen += 1
        unchanged = (line is None and view.change_count() == st.get('cc')
                     and pv.entry_vp is not None
                     and abs(view.viewport_position()[1] - pv.entry_vp[1]) < 1)
        if line is None:
            line = _top_line(pv)
            screen_y = 0.0
            at_top = navigation.at_top(pv.ys, *_top_basis(pv))
        else:
            at_top = False
    else:
        line = 0 if line is None else line
        at_top = screen_y is None
    sel = _restore_view_state(view, st)
    _detach_if_unused(view)
    store = _store_get()
    if store is not None and view.file_name():
        store.remove(view.file_name())
    if unchanged:
        view.sel().clear()
        view.sel().add_all(sel)
        if 'vp_pt' in st:
            _set_viewport_at(view, st['vp_pt'], -float(st.get('vp_off', 0.0)), x=st['vp'][0])
        else:
            _set_viewport_at(view, 0, -float(st['vp'][1]))
    else:
        line = max(0, min(int(line), view.rowcol(view.size())[0]))
        pt = view.text_point(line, 0)
        _set_viewport_at(view, pt, float(screen_y or 0.0), at_top=at_top)
        view.sel().clear()
        vr = view.visible_region()
        if not given and sel and all(vr.contains(r) for r in sel):
            view.sel().add_all(sel)
        else:
            view.sel().add(sublime.Region(pt))
    place_edit_button(view)
    return True


def _set_viewport_at(view, pt, screen_y, at_top=False, x=0.0):
    """Puts text point pt at screen_y (y 0 when at_top).

    Leaving the preview changes wrap/gutter settings and ST lays the text out again over the
    next ticks, re-anchoring the viewport; the y is recomputed from pt and applied again.
    """
    def apply():
        if view.is_valid():
            y = 0.0 if at_top else max(0.0, view.text_to_layout(pt)[1] - screen_y)
            view.set_viewport_position((x, y), False)
    apply()
    sublime.set_timeout(apply, 0)
    sublime.set_timeout(apply, 50)


def toggle(view, line=None, screen_y=None):
    """Flips the mode. line/screen_y (optional) is the reference row and its screen height."""
    if is_preview(view):
        return exit(view, line, screen_y)
    return enter(view, line, screen_y)


# ---------------------------------------------------------------- buffer listeners


def _attach(view):
    buf = view.buffer()
    if _listener_cls is None or buf.id() in _listeners:
        return
    lst = _listener_cls()
    lst.attach(buf)
    _listeners[buf.id()] = lst


def _detach_if_unused(view, closing=False):
    buf = view.buffer()
    others = [v for v in buf.views() if v.id() in _views and not (closing and v.id() == view.id())]
    if others:
        return
    lst = _listeners.pop(buf.id(), None)
    if lst is not None and lst.is_attached():
        lst.detach()


def _buffer_previews(buffer):
    return [_views[v.id()] for v in buffer.views() if v.id() in _views]


def on_text_changed(buffer):
    for pv in _buffer_previews(buffer):
        _refold(pv)
        if _holding(pv):
            _hold_reanchor(pv)
        _debounced(pv.view.id(), 'edit', EDIT_DEBOUNCE_MS, lambda pv=pv: _edit_due(pv))


def _is_visible(pv):
    vid = pv.view.id()
    return any(v.id() == vid for v in _visible_views())


def _mark_stale(pv, kind):
    if kind == 'full' or pv.stale is None:
        pv.stale = kind


def _edit_due(pv):
    if _views.get(pv.view.id()) is not pv:
        return
    if _is_visible(pv):
        _update(pv)
    else:
        _mark_stale(pv, 'update')


def _redraw(pv, reason):
    """Full redraw now when the preview is on screen, else owed until it is shown."""
    if _views.get(pv.view.id()) is not pv:
        return
    if _is_visible(pv):
        _rerender(pv, reason)
    else:
        _mark_stale(pv, 'full')


def _flush_stale(pv):
    kind, pv.stale = pv.stale, None
    if kind == 'full':
        _rerender(pv, 'stale')
    elif kind == 'update':
        _update(pv)


def _update(pv):
    if _views.get(pv.view.id()) is not pv:
        return
    top = _capture_top(pv) if pv.done else pv.top
    _start_render(pv, pos=top, reason='edit')


def on_reload(buffer, reason='reload'):
    """Reload wipes the fold and every phantom; redraw from scratch at once."""
    for pv in _buffer_previews(buffer):
        view = pv.view
        st = view.settings().get(STATE_KEY)
        if st and not st.get('reloaded'):
            st['reloaded'] = True
            _set_state(view, st)
        _fold(view, pv.layout or 'B', view.size(), view.line(0).b)
        pv.stats['reload_t0'] = time.perf_counter()
        pv.btn_pid = None
        pv.pids, pv.ys, pv.added = [], [], []
        pv.done = False   # the table is empty until the redraw: done readers index pv.ys
        pv.spacer_pid, pv.spacer_h, pv.stage = None, 0.0, None   # wiped with the other phantoms
        _start_render(pv, full=True, pos=pv.top, reason=reason)
        if pv.pending is not None and view.size() > view.line(0).b:
            # First callback after ST erased the phantoms: until here the old drawing was on
            # screen, from here the hold is. A one-line document has a single
            # block and its end is the block anchor, where the spacer would sit above the blocks.
            _hold_start(pv)


def on_revert(buffer):
    on_reload(buffer, 'revert')


# ---------------------------------------------------------------- view events


def _navigate(view_id, href):
    view = sublime.View(view_id)
    if view.is_valid():
        on_navigate(view, href)


def on_navigate(view, href):
    """Phantom link handler for both modes: toggle button, edit links (double click) and
    document links."""
    if href == TOGGLE_HREF:
        toggle(view)
        return
    if not is_preview(view):
        return
    judge = _judges.get(view.id())
    if judge is None:
        judge = _judges[view.id()] = preview_input.ClickJudge(CLICK_S)
    action = judge.feed(href, time.perf_counter())
    if action == 'edit_double':
        _edit_at(view, navigation.classify_link(href)[1])
    elif action == 'open':
        _open_link(view, href)


def _edit_at(view, row):
    """Double click: row goes to the screen height its proportional preview y had."""
    pv = _views.get(view.id())
    screen_y = 0.0
    if pv is not None and pv.starts and pv.ys:
        k = navigation.block_for_line(pv.starts, row)
        if k < len(pv.ys) and _h_of(pv, k) is not None:
            starts, ends, ys, total = _drawn_table(pv, k)
            screen_y = navigation.screen_y_for_line(
                starts, ends, ys, total, row, view.viewport_position()[1],
                view.viewport_extent()[1], view.line_height())
    exit(view, row, screen_y)


def _open_link(view, href):
    link = navigation.classify_link(href)
    kind = link[0]
    if kind == 'web':
        webbrowser.open(link[1])
    elif kind == 'anchor':
        if not show_anchor(view, link[1], animate=True):
            show_message(view, 'Heading not found: #%s' % link[1])
    elif kind in ('footnote', 'footnote_back'):
        frag = href[1:]
        if not show_anchor(view, frag, animate=True):
            show_message(view, 'Footnote not found: #%s' % frag)
    elif kind == 'file':
        _open_file_link(view, link[1], link[2])
    else:
        show_message(view, 'Cannot open link: %s' % href)


def _fragment_index(doc, fragment):
    """Block of a same-document fragment: a heading slug or a footnote target (fn-n, fnref-n)."""
    notes, refs = blocks.footnote_blocks(doc)
    return navigation.fragment_block(fragment, [b.slug for b in doc.blocks], notes, refs)


def show_anchor(view, slug, animate=False):
    """Scrolls a preview view to the block a fragment names (heading slug, fn-n or fnref-n),
    once it is drawn. Returns False when the view has no such block."""
    pv = _views.get(view.id())
    if pv is None or pv.doc is None:
        return False
    k = _fragment_index(pv.doc, slug)
    if k is None:
        return False
    if k < len(pv.ys):
        scroll_to(view, 0.0 if k == 0 else pv.ys[k], animate)
    else:
        pv.pending = ('slug', slug)
    return True


def _open_file_link(view, path, slug):
    base = view.file_name()
    if not base:
        show_message(view, 'Cannot open %s: the document is not saved in a folder' % path)
        return
    target = navigation.resolve_file_link(os.path.dirname(base), path)
    if not os.path.isfile(target):
        show_message(view, 'File not found: %s' % target)
        return
    tv = _window(view).open_file(target)
    _when_loaded(tv, lambda: _show_opened(tv, slug))


def _when_loaded(view, fn, n=0):
    if not view.is_valid() or n > LOAD_WAIT_LIMIT:
        return
    if view.is_loading():
        sublime.set_timeout(lambda: _when_loaded(view, fn, n + 1), LOAD_WAIT_MS)
        return
    # on_load runs in the same turn as the load finishing; it may enter the remembered mode.
    sublime.set_timeout(fn, 0)


def _show_opened(view, slug):
    """A linked target file finished loading: show it in the preview, at the anchor if any."""
    if not view.is_valid() or not is_applicable(view):
        return
    if is_preview(view) and view.id() not in _views:
        _restore(view)
    pv = _views.get(view.id())
    if pv is None:
        enter(view, pos=('slug', slug) if slug else None)
        return
    if slug:
        pv.pending = ('slug', slug)
        if pv.doc is not None:
            _try_position(pv)


def show_message(view, text):
    """Status bar message of this view for MSG_MS."""
    vid = view.id()
    token = _msg_tokens.get(vid, 0) + 1
    _msg_tokens[vid] = token
    view.set_status(MSG_KEY, text)

    def clear():
        if _msg_tokens.get(vid) == token:
            del _msg_tokens[vid]
            if view.is_valid():
                view.erase_status(MSG_KEY)
    sublime.set_timeout(clear, MSG_MS)


def show_hint(view):
    if is_preview(view):
        show_message(view, HINT_MSG)


def on_text_command(view, name, args):
    """Preview: blocked and editing commands become a no-op, caret moves become pixel scrolls."""
    if not is_preview(view):
        return None
    action = preview_input.text_command_action(name, args)
    if action == 'block':
        return (NOOP_COMMAND, {})
    if action == 'hint':
        return (NOOP_COMMAND, {'hint': True})
    if action == 'scroll':
        return (SCROLL_COMMAND, {'name': name, 'args': args or {}})
    if action == 'edit_then_run':
        exit(view)
    return None


def preview_scroll(view, name, args):
    """move/move_to arguments as a pixel scroll of a preview view; returns the new y or None."""
    pv = _views.get(view.id())
    if pv is None or _holding(pv):
        return None   # held: the viewport y is no position, and the hold ends soon by itself
    vh = view.viewport_extent()[1]
    target = preview_input.scroll_target(
        name, args, y=view.viewport_position()[1], line_h=view.line_height(), viewport_h=vh,
        max_y=max(0.0, view.layout_extent()[1] - vh))
    if target is None:
        return None
    return scroll_to(view, target)


def on_selection_modified(view):
    # The preview never has a caret or selection (commands that were not intercepted).
    if len(view.sel()) and is_preview(view):
        view.sel().clear()


def on_window_command(window, name, args):
    """Find panels and goto line/definition switch the active preview to the source first; the
    original command then runs on the source. Goto Symbol (@) becomes the heading panel."""
    view = window.active_view()
    if view is None or not is_preview(view):
        return None
    action = preview_input.window_command_action(name, args, phase=2)
    if action == 'edit_then_run':
        exit(view)
    elif action == 'heading_panel':
        return (HEADINGS_COMMAND, {})
    return None


def zoom(view, step):
    """Editor zoom (font_size +-1) that, in a target view, also scales font_scale by the same
    ratio; both are saved. Other views get ST's own command, since the mouse binding is global."""
    if view is None or not is_applicable(view):
        window = _window(view) if view is not None else sublime.active_window()
        if window is not None:
            window.run_command('increase_font_size' if step > 0 else 'decrease_font_size')
        return
    prefs = sublime.load_settings(PREFS_FILE)
    old = prefs.get('font_size') or 10   # kept as written (an int stays an int)
    new = old + step
    if new < 1:
        return
    path = _zoom_file()
    anchor, scale = theme.zoom_scale(_zoom_anchor(), _font_scale(), old, new)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(list(anchor), f)
    prefs.set('font_size', new)
    sublime.save_settings(PREFS_FILE)
    _cfg().set('font_scale', scale)
    sublime.save_settings(SETTINGS_FILE)
    # After this step's own render has started: the neighbours of the new step are written then.
    sublime.set_timeout(_premake, 0)


def _on_goto_overlay(widget):
    """show_overlay does not reach on_window_command, so goto line/definition is caught when its
    input opens: the overlay is closed, the preview switched to the source and the overlay
    reopened so that it starts from the source view. Goto Symbol (@) closes the overlay and
    opens the heading panel instead."""
    window = widget.window()
    view = window.active_view() if window else None
    if view is None or not is_preview(view):
        return
    args = {'overlay': 'goto', 'text': widget.substr(sublime.Region(0, widget.size()))}
    action = preview_input.window_command_action('show_overlay', args, phase=2)
    if action == 'heading_panel':
        # The goto overlay may already have scrolled the view to its first symbol.
        y0 = view.viewport_position()[1]
        pv0 = _views.get(view.id())
        held = pv0 is not None and _holding(pv0)   # y0 is then no position

        def headings():
            if view.is_valid() and is_preview(view):
                window.run_command('hide_overlay')
                pv = _views.get(view.id())
                if pv is not None and _holding(pv):
                    _scroll(view, pv.hold_y)
                elif not held:
                    scroll_to(view, y0)
                show_headings(window, view, None if held else y0)
        sublime.set_timeout(headings, 0)
        return
    if action != 'edit_then_run':
        return

    def rerun():
        if view.is_valid() and is_preview(view):
            window.run_command('hide_overlay')
            exit(view)
            window.run_command('show_overlay', args)
    sublime.set_timeout(rerun, 0)


def _heading_items(heads):
    # Indent: two no-break spaces per level below h1.
    return [sublime.QuickPanelItem(' ' * 2 * (lvl - 1) + (text or ' '), annotation='h%d' % lvl)
            for _, lvl, text in heads]


def _scroll_block(pv, k):
    """Puts block k at the top of a preview (the toolbar stays visible for block 0)."""
    if k < len(pv.ys):
        scroll_to(pv.view, 0.0 if k == 0 else pv.ys[k])
    else:
        pv.pending = ('index', k)


def show_headings(window, view=None, y0=None):
    """Goto Symbol of a preview: a quick panel of its headings. Highlighting one scrolls to it,
    choosing one stays there, cancelling returns to where the view was (y0, default: now).
    The panel opens on the heading at or above the top of the view without moving it."""
    view = view or window.active_view()
    pv = _views.get(view.id()) if view is not None else None
    if pv is None or pv.doc is None:
        return False
    heads = blocks.headings(pv.doc)
    if not heads:
        show_message(view, 'No headings')
        return True
    held = _holding(pv)
    p0 = pv.pending
    if held:
        # The held viewport y is no position: the panel opens on the position being restored.
        vy, pl = _top_basis(pv)
        top = (navigation.block_for_line(pv.starts, pl) if pl is not None
               else bisect.bisect_right(pv.ys, vy + 0.5) - 1)
    else:
        if y0 is None:
            y0 = view.viewport_position()[1]
        top = bisect.bisect_right(pv.ys, y0 + 0.5) - 1
    sel = 0
    for i, (k, _, _) in enumerate(heads):
        if k <= top:
            sel = i
    opening = [True]

    def on_highlight(i):
        # show_quick_panel calls this synchronously while opening (for item 0, then the
        # selection); opening the panel does not move the view.
        if opening[0]:
            return
        if view.is_valid() and _views.get(view.id()) is pv and 0 <= i < len(heads):
            _scroll_block(pv, heads[i][0])

    def on_select(i):
        if not view.is_valid() or _views.get(view.id()) is not pv:
            return
        if i < 0:
            if held:
                _hold_resume(pv, p0)
            else:
                pv.pending = None
                scroll_to(view, y0)
        else:
            _scroll_block(pv, heads[i][0])

    try:
        window.show_quick_panel(_heading_items(heads), on_select, 0, sel, on_highlight,
                                'Go to heading')
    finally:
        opening[0] = False
    return True


def _restore(view):
    """Brings back a view whose state says preview but has no drawing in this plugin run."""
    st = view.settings().get(STATE_KEY)
    if not st or view.id() in _views or view.is_loading():
        return
    if st.get('mode') == 'resume':
        view.settings().erase(STATE_KEY)
        enter(view, pos=_pos_from_record(st.get('top')))
        return
    if st.get('mode') != 'preview':
        return
    if not is_applicable(view) or view.viewport_extent()[0] <= 0:
        return
    pv = _Preview(view)
    pv.stats['enter_t0'] = time.perf_counter()
    _timeline.setdefault('restore', time.time())
    _views[view.id()] = pv
    _attach(view)
    view.sel().clear()
    view.set_status(STATUS_KEY, 'Preview')
    _start_render(pv, full=True, pos=_pos_from_record(st.get('top')), reason='restore')


def on_load(view):
    if not _alive[0]:
        return
    if view.settings().get(STATE_KEY):
        _restore(view)
        return
    if not is_applicable(view):
        return
    store = _store_get()
    rec = store.get(view.file_name()) if store is not None and view.file_name() else None
    if rec is not None:
        enter(view, pos=('block', int(rec['line'])))
    else:
        place_edit_button(view)


def on_activated(view):
    if _alive[0] and view.element() == GOTO_INPUT:
        _on_goto_overlay(view)
        return
    if not _alive[0] or view.is_loading() or view.element() is not None:
        return
    if view.settings().get(STATE_KEY):
        if _setting_kind() is None:
            _rejudge(view)
        _restore(view)
        pv = _views.get(view.id())
        if pv is not None and view.viewport_extent()[0] > 0:
            if _geom_changed(pv):
                if _geom(view)[1] != pv.geom[1]:
                    layout.clear_cache()
                _rerender(pv, 'geometry')
            elif pv.stale:
                _flush_stale(pv)
        return
    if is_applicable(view):
        info = _edit_buttons.get(view.id())
        if info is None or info['geom'] != _edit_geom(view):
            place_edit_button(view)
    elif view.id() in _edit_buttons:
        remove_edit_button(view)


def on_deactivated(view):
    pv = _views.get(view.id())
    if pv is not None and pv.done:
        _remember(pv)


def _remember(pv):
    store = _store_get()
    if store is not None and pv.view.file_name():
        store.put(pv.view.file_name(), _top_line(pv))


def on_pre_close(view):
    vid = view.id()
    pv = _views.get(vid)
    if pv is not None:
        if pv.done:
            _remember(pv)
        pv.gen += 1
        _detach_if_unused(view, closing=True)
        del _views[vid]
    _edit_buttons.pop(vid, None)
    _pending_enter.pop(vid, None)
    _judges.pop(vid, None)
    _msg_tokens.pop(vid, None)


def on_pre_close_window(window):
    layout.close_window(window)
    highlight.close_window(window)


def on_post_save(view):
    on_activated(view)


def query_context(view, key, operator, operand, match_all):
    if key == 'mdgh_preview.applicable':
        value = is_applicable(view)
    elif key == 'mdgh_preview.preview':
        value = is_preview(view)
    else:
        return None
    if operand is None:
        operand = True
    if operator == sublime.OP_EQUAL:
        return value == operand
    if operator == sublime.OP_NOT_EQUAL:
        return value != operand
    return None


# ---------------------------------------------------------------- polling


def _visible_views():
    for w in sublime.windows():
        for g in range(w.num_groups()):
            v = w.active_view_in_group(g)
            if v is not None:
                yield v


def _poll():
    if not _alive[0]:
        return
    try:
        for v in _visible_views():
            _check_view(v)
    finally:
        sublime.set_timeout(_poll, POLL_MS)


def _check_view(view):
    vid = view.id()
    pv = _views.get(vid)
    if pv is not None:
        if view.viewport_extent()[0] <= 0:
            return
        if _geom_changed(pv):
            if _geom(view)[1] != pv.geom[1]:
                layout.clear_cache()   # widths measured at the old font size
            _debounced(vid, 'geom', GEOM_DEBOUNCE_MS, lambda: _geom_rerender(pv))
        elif pv.stale:
            _flush_stale(pv)
        elif pv.done:
            _persist_top(pv)
        return
    if view.settings().get(STATE_KEY):
        _restore(view)
        return
    if view.element() is not None:
        return
    info = _edit_buttons.get(vid)
    applicable = is_applicable(view)
    if not applicable:
        if info is not None:
            remove_edit_button(view)
        return
    if info is None or info['geom'] != _edit_geom(view):
        _debounced(vid, 'geom', GEOM_DEBOUNCE_MS, lambda: place_edit_button(view))


def _geom_changed(pv):
    """The view's geometry differs from the drawn one. A render that has not read the geometry
    yet (parse, scheme indexing) reads the current one itself."""
    return pv.geom is not None and not pv.applying and _geom(pv.view) != pv.geom


def _geom_rerender(pv):
    if pv.view.is_valid() and _geom_changed(pv):   # the debounce may outlive the change
        _rerender(pv, 'geometry')


def _rerender(pv, reason):
    if _views.get(pv.view.id()) is not pv:
        return
    top = _capture_top(pv) if pv.done else pv.top
    _start_render(pv, full=True, pos=top, reason=reason)


def _on_settings_change():
    if not _alive[0]:
        return
    snapshot = _cfg().to_dict()
    if snapshot == _cfg_seen[0]:
        return   # ST reports the saved file again with the same values
    _cfg_seen[0] = snapshot
    layout.clear_cache()
    _css_cache[0] = None
    for pv in list(_views.values()):
        _rejudge(pv.view, rerender=False)
        _redraw(pv, 'settings')
    for v in _visible_views():
        if not is_preview(v):
            if is_applicable(v):
                _edit_buttons.pop(v.id(), None)
                place_edit_button(v)
            else:
                remove_edit_button(v)


def _on_prefs_change():
    """auto: a global color_scheme (or anything else in Preferences) changed."""
    if not _alive[0] or _setting_kind() is not None:
        return

    def later():
        if _alive[0]:
            for pv in list(_views.values()):
                _rejudge(pv.view)
    # Inside the on_change callback an existing panel still reports the old style; it is
    # updated once the settings call returns (measured).
    sublime.set_timeout(later, 0)


# ---------------------------------------------------------------- lifecycle


def plugin_loaded(listener_cls):
    global _listener_cls
    _listener_cls = listener_cls
    _alive[0] = True
    _timeline.setdefault('plugin_loaded', time.time())
    _cfg().add_on_change(STATUS_KEY, _on_settings_change)
    sublime.load_settings(PREFS_FILE).add_on_change(STATUS_KEY, _on_prefs_change)
    try:
        _premake()
    except Exception as e:   # a measurement failure must not stop recovery below
        print('Markdown GitHub Preview: could not prepare the color scheme: %r' % (e,))
    for v in _visible_views():
        if v.settings().get(STATE_KEY):
            _restore(v)
        else:
            on_activated(v)
    sublime.set_timeout(_poll, POLL_MS)


def plugin_unloaded():
    """Returns every preview to the source so no view stays folded if the package goes away;
    a resume marker lets the next load reopen the preview at the same place."""
    _alive[0] = False
    _cfg().clear_on_change(STATUS_KEY)
    sublime.load_settings(PREFS_FILE).clear_on_change(STATUS_KEY)
    theme.destroy_auto_panels()
    highlight.destroy_all()
    remote.shutdown()
    for w in sublime.windows():
        for v in w.views():
            st = v.settings().get(STATE_KEY)
            if st and st.get('mode') == 'preview':
                pv = _views.pop(v.id(), None)
                top = st.get('top')
                if pv is not None and pv.done:
                    _persist_top(pv)
                    top = (v.settings().get(STATE_KEY) or {}).get('top', top)
                sel = _restore_view_state(v, st)
                if sel:
                    v.sel().clear()
                    v.sel().add_all(sel)
                v.settings().set(STATE_KEY, {'mode': 'resume', 'top': top})
            v.erase_phantoms(EDIT_BUTTON_KEY)
    for lst in list(_listeners.values()):
        if lst.is_attached():
            lst.detach()
    _listeners.clear()
    _views.clear()
    _edit_buttons.clear()
    layout.destroy_all()


# ---------------------------------------------------------------- queries for other units


def block_table(view):
    """Drawn block geometry of a preview view, or None.

    {'starts', 'ends': source row ranges per block, 'ys': top y per drawn block,
     'total_h': bottom of the last block (valid when done), 'done': all blocks drawn,
     'slugs': heading slug or None per block, 'keys': Block.key per block}
    """
    pv = _views.get(view.id())
    if pv is None or pv.doc is None:
        return None
    return {'starts': list(pv.starts), 'ends': list(pv.ends), 'ys': list(pv.ys),
            'total_h': pv.total_h, 'done': pv.done, 'keys': list(pv.keys),
            'slugs': [b.slug for b in pv.doc.blocks]}


def scroll_to(view, y, animate=False):
    """Pixel scroll of a preview view, clamped to the drawn content."""
    pv = _views.get(view.id())
    held = pv is not None and _holding(pv)
    spacer_h = pv.spacer_h if pv is not None else 0.0
    max_y = max(0.0, view.layout_extent()[1] - spacer_h - view.viewport_extent()[1])
    y = min(max(0.0, float(y)), max_y)
    # An animation from the held y would pass the clamped viewport once the spacer is gone.
    view.set_viewport_position((0.0, y), animate and not held)
    if pv is not None:
        pv.pending = None
        _hold_end(pv)
    return y


def debug_info(view):
    """Diagnostics for development runners."""
    pv = _views.get(view.id())
    out = {
        'preview': is_preview(view), 'state': view.settings().get(STATE_KEY),
        'layout_extent': list(view.layout_extent()), 'viewport_extent': list(view.viewport_extent()),
        'viewport': list(view.viewport_position()), 'line_height': view.line_height(),
        'folds': [[r.a, r.b] for r in view.folded_regions()], 'size': view.size(),
        'scheme_waits': dict(_scheme_waits),
        'timeline': {k: time.strftime('%H:%M:%S', time.localtime(t)) + '.%03d' % (t % 1 * 1000)
                     for k, t in _timeline.items()},
        'edit_button': dict(_edit_buttons[view.id()]) if view.id() in _edit_buttons else None,
        'edit_button_regions': [[r.a, r.b] for r in view.query_phantoms(
            [p for p in [(_edit_buttons.get(view.id()) or {}).get('pid')] if p is not None])],
    }
    if pv is not None:
        out.update(layout=pv.layout, anchor=pv.anchor, anchor_now=_anchor_now(pv), extra=pv.extra,
                   blocks=len(pv.ids) if pv.doc else 0, phantoms=len(pv.pids), ys=list(pv.ys),
                   total_h=pv.total_h, done=pv.done, gen=pv.gen, geom=list(pv.geom or ()),
                   btn_pid=pv.btn_pid, btn_html=pv.btn_html, pending=repr(pv.pending),
                   hold=_holding(pv), spacer_h=pv.spacer_h, staging=pv.stage is not None,
                   top=repr(pv.top)[:200],
                   stats={k: v for k, v in pv.stats.items() if not k.endswith('t0')},
                   starts=list(pv.starts), ends=list(pv.ends),
                   phantom_regions=[[r.a, r.b] for r in view.query_phantoms(pv.pids[:3])],
                   toolbar_regions=[[r.a, r.b] for r in view.query_phantoms(
                       [pv.btn_pid] if pv.btn_pid is not None else [])])
    return out
