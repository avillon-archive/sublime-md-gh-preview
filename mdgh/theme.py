# -*- coding: utf-8 -*-
"""Theme variables, phantom CSS assembly and preview color scheme.

Everything above "ST resources" is pure; the functions below it import sublime lazily.
"""
import hashlib
import json
import os
import re

_PLACEHOLDER = re.compile(r'\{(c|px|lh)\.([A-Za-z0-9_-]+)\}|\{(font_body|font_mono)\}')
_REQUIRED = ('name', 'kind', 'base_px', 'colors', 'px', 'lh')

# Every global color of the preview scheme equals the background, so the folded source text
# that stays on screen and the caret/selection are invisible.
_HIDDEN_GLOBALS = (
    'foreground', 'fold_marker', 'caret', 'line_highlight', 'selection', 'selection_border',
    'inactive_selection', 'misspelling', 'invisibles', 'guide', 'active_guide', 'stack_guide',
    'highlight', 'find_highlight', 'brackets_foreground', 'tags_foreground',
)


def _shift_hex(color):
    # minihtml drops a border-left whose color equals the horizontal border color.
    b = int(color[5:7], 16)
    b = b + 1 if b < 255 else b - 1
    return '%s%02x' % (color[:5], b)


def load_vars(json_text):
    v = json.loads(json_text)
    for k in _REQUIRED:
        if k not in v:
            raise ValueError('theme is missing %r' % k)
    colors = v['colors']
    colors.setdefault('table-border-v', _shift_hex(colors['table-border']))
    return v


GITHUB_BODY_PX = 16.0


def body_px(font_scale=1.0):
    """CSS px of the preview body text: GitHub's size x font_scale."""
    return GITHUB_BODY_PX * font_scale


def zoom_scale(anchor, font_scale, old_font_size, new_font_size):
    """(anchor, font_scale) after a zoom step moved the editor font_size from old to new; the
    preview scales by the same ratio. anchor = (font_size, font_scale) every step is computed
    from, so returning to a font_size gives back exactly its font_scale (stepping from the last
    rounded value would drift). A font_scale the anchor does not give at old_font_size (edited by
    hand, or font_size changed outside zoom) starts a new anchor."""
    def at(a, fs):
        return round(a[1] * fs / a[0], 4)
    if anchor is None or at(anchor, old_font_size) != round(font_scale, 4):
        anchor = (old_font_size, font_scale)
    return anchor, at(anchor, new_font_size)


def pre_px(vars, body):
    """CSS px of code block text; the caller measures h_mono at this size."""
    return vars['px']['pre'] * body / vars['base_px']


def line_height_css(p_px, h_px):
    """minihtml renders a line at (h + L) / 2 when L > h, so reaching p needs L = 2p - h."""
    if p_px <= h_px:
        return None
    return 2 * p_px - h_px


def _fmt(v):
    return '%gpx' % round(v, 2)


def scaled_lengths(vars, body_px):
    """CSS lengths (px) at body_px: the theme's px values plus derived ones. Both the CSS and the
    renderer's width arithmetic read them, so a table or list lays out with the CSS it is drawn by."""
    scale = body_px / vars['base_px']
    lengths = {k: v * scale for k, v in vars['px'].items()}
    # ST adds 4px around every block phantom (3 above, 1 below); the wrapper's own padding
    # supplies the rest of GitHub's 16px gap.
    lengths['blk_pb'] = max(0.0, lengths['block_gap'] - 4)
    # Table cells are inline-blocks whose vertical padding and 1px border minihtml leaves out of
    # the line box; the row div makes that room, so both use the same whole-px values.
    for k in ('cell_px', 'cell_py'):
        lengths[k] = float(round(lengths[k]))
    lengths['row_pt'] = lengths['cell_py'] + 1
    lengths['row_pb'] = lengths['cell_py']
    lengths['row_pb_last'] = lengths['cell_py'] + 1
    return lengths


# Lengths the renderer's layout arithmetic needs (RenderContext.metrics).
LAYOUT_METRICS = ('code', 'code_px', 'cell_px', 'indent', 'bar', 'quote_pad', 'fn', 'fn_indent',
                  'sup', 'check')


def layout_metrics(vars, body_px):
    """Sorted (name, px) pairs of LAYOUT_METRICS at body_px; hashable for the render cache key."""
    lengths = scaled_lengths(vars, body_px)
    return tuple(sorted((k, round(lengths[k], 3)) for k in LAYOUT_METRICS))


def build_css(vars, base_css, *, body_px, font_body, font_mono, h_body, h_mono, user_css):
    lengths = scaled_lengths(vars, body_px)

    def decl(name):
        if name == 'body':
            lh = line_height_css(vars['lh']['body'] * body_px, h_body)
        elif name == 'pre':
            lh = line_height_css(vars['lh']['pre'] * lengths['pre'], h_mono)
        else:
            raise KeyError('lh.' + name)
        return '' if lh is None else 'line-height: %s;' % _fmt(lh)

    def face(name):
        return '"%s"' % name.replace('"', '')

    def repl(m):
        if m.group(3) == 'font_body':
            return face(font_body)
        if m.group(3) == 'font_mono':
            return face(font_mono)
        kind, name = m.group(1), m.group(2)
        if kind == 'c':
            return vars['colors'][name]
        if kind == 'px':
            return _fmt(lengths[name])
        return decl(name)

    css = _PLACEHOLDER.sub(repl, base_css)
    return '\n'.join([css] + list(user_css))


def build_scheme(vars, phantom_css):
    bg = vars['colors']['bg']
    g = {'background': bg}
    for k in _HIDDEN_GLOBALS:
        g[k] = bg
    g['phantom_css'] = phantom_css
    return {'name': 'Markdown GitHub Preview ' + vars['name'], 'globals': g, 'rules': []}


def scheme_file_name(theme_name, scheme):
    digest = hashlib.sha1(json.dumps(scheme, sort_keys=True, ensure_ascii=False)
                          .encode('utf-8')).hexdigest()[:12]
    return '%s-%s.hidden-color-scheme' % (theme_name, digest)


# ---------------------------------------------------------------- theme choice

THEME_SETTINGS = ('github-light', 'github-dark', 'auto')
KINDS = ('light', 'dark')


def theme_name(kind):
    """Bundled theme file name of a kind ('light' | 'dark')."""
    return 'github-' + kind


def setting_kind(setting):
    """Kind fixed by the `theme` setting, or None for 'auto' (and unknown values: None too, the
    caller treats them as the default)."""
    for k in KINDS:
        if setting == theme_name(k):
            return k
    return None


def is_dark(color):
    """True when a '#rgb' / '#rrggbb[aa]' color has perceived brightness < 0.5."""
    c = (color or '').strip().lstrip('#')
    if len(c) in (3, 4):
        c = ''.join(ch * 2 for ch in c[:3])
    try:
        r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return False
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0 < 0.5


def collect_user_css(paths, load):
    """Texts of the custom_css files in order. load(path) returns the text or raises OSError /
    IOError for a missing file. Returns (texts, missing paths)."""
    texts, missing = [], []
    for p in paths or []:
        if not isinstance(p, str) or not p:
            continue
        try:
            texts.append(load(p))
        except (OSError, IOError):
            missing.append(p)
    return texts, missing


def css_digest(texts):
    return hashlib.sha1('\0'.join(texts).encode('utf-8')).hexdigest()[:12]


# ---------------------------------------------------------------- icons

ICON_NAMES = ('preview', 'edit', 'check-on', 'check-off', 'alert-note', 'alert-tip',
              'alert-important', 'alert-warning', 'alert-caution')

# Package folder name as ST sees it; every Packages/<name>/... path is built from this.
PACKAGE = __name__.split('.')[0]
SCHEME_EXT = '.hidden-color-scheme'


def resource_path(rel):
    return 'Packages/%s/%s' % (PACKAGE, rel)


def icon_html(name, kind, size_px, extra_attrs=''):
    """minihtml <img> of a bundled icon (PNG drawn at 2x; width/height give the display size).

    minihtml shows package images through res://Packages/... (measured; a bare
    Packages/... path shows the broken-image glyph)."""
    if name not in ICON_NAMES:
        raise ValueError('unknown icon %r' % (name,))
    if kind not in KINDS:
        raise ValueError('unknown icon kind %r' % (kind,))
    size = int(round(size_px))
    extra = (' ' + extra_attrs.strip()) if extra_attrs and extra_attrs.strip() else ''
    return '<img src="res://%s" width="%d" height="%d"%s>' % (
        resource_path('icons/%s-%s.png' % (name, kind)), size, size, extra)


# ---------------------------------------------------------------- ST resources


def load_theme(name):
    """(vars, base_css) of a bundled theme."""
    import sublime
    vars = load_vars(sublime.load_resource(resource_path('themes/%s.json' % name)))
    base = sublime.load_resource(resource_path('themes/base.css'))
    return vars, base


def load_css_file(path):
    """Text of a custom_css entry: a resource path (Packages/...) or an absolute file path."""
    import sublime
    if path.startswith('Packages/'):
        return sublime.load_resource(path)
    p = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isabs(p):
        raise FileNotFoundError(path)
    with open(p, encoding='utf-8') as f:
        return f.read()


AUTO_PANEL = 'mdgh_auto'


def judge_kind(window, syntax, color_scheme=None):
    """'dark' | 'light' of the editor scheme a view would run with outside the preview.

    A preview view runs the preview scheme, so the judgement uses a hidden panel with the view's
    syntax (syntax-specific color_scheme applies to it) and the view-level color_scheme the view
    had before the preview, if any."""
    panel = window.find_output_panel(AUTO_PANEL)
    if panel is None:
        panel = window.create_output_panel(AUTO_PANEL, True)
    s = panel.settings()
    if syntax is not None and panel.syntax() != syntax:
        panel.assign_syntax(syntax)
    if color_scheme:
        if s.get('color_scheme') != color_scheme:
            s.set('color_scheme', color_scheme)
    else:
        s.erase('color_scheme')
    return 'dark' if is_dark(panel.style().get('background')) else 'light'


def destroy_auto_panels():
    import sublime
    for w in sublime.windows():
        if w.find_output_panel(AUTO_PANEL) is not None:
            w.destroy_output_panel(AUTO_PANEL)


def scheme_dir():
    import sublime
    return os.path.join(sublime.packages_path(), 'User', PACKAGE)


def write_scheme(theme_name, scheme):
    """Writes the scheme under its content hash (never rewrites an existing name) and returns
    its resource path."""
    name = scheme_file_name(theme_name, scheme)
    d = scheme_dir()
    path = os.path.join(d, name)
    if not os.path.exists(path):
        os.makedirs(d, exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(scheme, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    return 'Packages/User/%s/%s' % (PACKAGE, name)


def scheme_ready(res):
    """True once ST indexed the file; assigning a scheme before that raises an
    'Error loading colour scheme' dialog."""
    import sublime
    return res in sublime.find_resources(res.rsplit('/', 1)[-1])


SCHEME_KEEP_RECENT = 64


def stale_schemes(entries, keep, recent=SCHEME_KEEP_RECENT):
    """Names to delete from (name, mtime) entries: everything outside keep except the `recent`
    newest by mtime (ties: the name that sorts later is newer)."""
    candidates = sorted((e for e in entries if e[0] not in keep),
                        key=lambda e: (e[1], e[0]), reverse=True)
    return [name for name, _mtime in candidates[max(recent, 0):]]


def prune_schemes(keep):
    """Deletes generated scheme files whose resource path is not in keep, except the
    SCHEME_KEEP_RECENT most recently used: views of a closed project are not in keep, and
    reopening it with its scheme gone raises a modal error."""
    d = scheme_dir()
    try:
        names = os.listdir(d)
    except FileNotFoundError:
        return []
    keep_names = set()
    entries = []
    for n in names:
        if not n.endswith(SCHEME_EXT):
            continue
        if 'Packages/User/%s/%s' % (PACKAGE, n) in keep:
            keep_names.add(n)
        try:
            entries.append((n, os.path.getmtime(os.path.join(d, n))))
        except OSError:
            pass
    removed = []
    for n in stale_schemes(entries, keep_names):
        try:
            os.remove(os.path.join(d, n))
            removed.append(n)
        except OSError:
            pass
    return removed
