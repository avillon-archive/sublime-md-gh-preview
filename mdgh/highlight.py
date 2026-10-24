# -*- coding: utf-8 -*-
"""Syntax highlighting of fenced code: language aliases and token-to-minihtml assembly (pure),
and the hidden window panel that tokenizes code with an installed ST syntax (ST)."""
import html

# Fence info word (lower case) -> file name `find_syntax_for_file` resolves; anything else is
# tried as the extension itself ("x.<word>").
ALIASES = {
    'python': 'x.py', 'python3': 'x.py', 'py3': 'x.py', 'js': 'x.js', 'javascript': 'x.js',
    'node': 'x.js', 'jsx': 'x.jsx', 'ts': 'x.ts', 'typescript': 'x.ts', 'tsx': 'x.tsx',
    'bash': 'x.sh', 'sh': 'x.sh', 'shell': 'x.sh', 'zsh': 'x.sh', 'console': 'x.sh',
    'powershell': 'x.ps1', 'pwsh': 'x.ps1', 'batch': 'x.bat', 'cmd': 'x.bat',
    'markdown': 'x.md', 'yml': 'x.yml', 'rust': 'x.rs', 'golang': 'x.go', 'ruby': 'x.rb',
    'kotlin': 'x.kt', 'csharp': 'x.cs', 'c#': 'x.cs', 'c++': 'x.cpp', 'cplusplus': 'x.cpp',
    'objective-c': 'x.m', 'objc': 'x.m', 'dockerfile': 'Dockerfile', 'make': 'Makefile',
    'makefile': 'Makefile', 'jsonc': 'x.json', 'json5': 'x.json', 'html': 'x.html',
    'xml': 'x.xml', 'vue': 'x.vue', 'tex': 'x.tex', 'latex': 'x.tex', 'perl': 'x.pl',
    'text': None, 'txt': None, 'plain': None, 'plaintext': None, 'none': None,
}

_PANEL_NAME = 'mdgh_highlight'
_SCHEME = 'Packages/%s/schemes/github-code-%s.hidden-color-scheme'
_CACHE_LIMIT = 2000
_STYLE_LIMIT = 4096


def lang_of(info):
    """Language word of a fence info string ("python {x}" -> "python"), '' when none."""
    words = (info or '').strip().split()
    if not words:
        return ''
    w = words[0]
    if w.startswith('{') and len(w) > 1:    # ```{python}
        w = w[1:]
    return w.strip('{}.,').lower()


def file_name_for(lang):
    """File name to resolve the syntax with, or None for no highlighting."""
    lang = lang_of(lang)
    if not lang:
        return None
    if lang in ALIASES:
        return ALIASES[lang]
    return 'x.' + lang


def _span(txt, style):
    if style is None:
        return txt
    fg, bold, italic = style
    if bold:
        txt = '<b>%s</b>' % txt
    if italic:
        txt = '<i>%s</i>' % txt
    if fg:
        txt = '<span style="color:%s">%s</span>' % (fg, txt)
    return txt


def assemble(text, tokens, default_fg):
    """Per-line minihtml of `text` colored by `tokens`.

    tokens: (a, b, fg, bold, italic) ascending, offsets into text. Text between tokens is kept
    unstyled. A style equal to the default (the color the surrounding text already has) is
    dropped, neighbours with equal style merge, and spans never cross a line break.
    Returns text.count('\\n') + 1 strings."""
    default_fg = (default_fg or '').lower()
    segs = []

    def add(s, style):
        if not s:
            return
        if segs and segs[-1][1] == style:
            segs[-1][0] += s
        else:
            segs.append([s, style])

    pos = 0
    for a, b, fg, bold, italic in tokens:
        a = max(a, pos)
        if b <= a:
            continue
        add(text[pos:a], None)
        fg = fg if fg and fg.lower() != default_fg else None
        style = (fg, bool(bold), bool(italic))
        add(text[a:b], None if style == (None, False, False) else style)
        pos = b
    add(text[pos:], None)

    lines = [[]]
    for s, style in segs:
        parts = s.split('\n')
        for i, part in enumerate(parts):
            if i:
                lines.append([])
            if part:
                lines[-1].append(_span(html.escape(part, quote=False), style))
    return [''.join(parts) for parts in lines]


# ---------------------------------------------------------------- ST side

_panels = {}      # window id -> (panel view, scheme path currently set)
_cache = {}       # (kind, file name, code) -> tuple of line html, or None (no highlighting)
_styles = {}      # (scheme path, scope) -> (foreground, bold, italic)
_stats = {'panel_runs': 0, 'ms': 0.0, 'style_calls': 0, 'style_hits': 0}


def _panel(window, kind):
    entry = _panels.get(window.id())
    view = entry[0] if entry else None
    if view is None or not view.is_valid():
        view = window.create_output_panel(_PANEL_NAME, unlisted=True)
        s = view.settings()
        s.set('word_wrap', False)
        s.set('is_widget', True)
        view.set_scratch(True)
        entry = None
    from . import theme
    scheme = _SCHEME % (theme.PACKAGE, kind)
    if entry is None or entry[1] != scheme:
        view.settings().set('color_scheme', scheme)
    _panels[window.id()] = (view, scheme)
    return view, scheme


def _style(p, scheme, scope):
    key = (scheme, scope)
    style = _styles.get(key)
    if style is None:
        st = p.style_for_scope(scope)
        style = (st.get('foreground'), st.get('bold'), st.get('italic'))
        if len(_styles) >= _STYLE_LIMIT:
            _styles.clear()
        _styles[key] = style
        _stats['style_calls'] += 1
    else:
        _stats['style_hits'] += 1
    return style


def lines(window, kind, lang, code):
    """Highlighted html per code line (len == code.count('\\n') + 1), or None for plain text.

    The panel is only written on a cache miss, so unchanged blocks cost nothing on re-render."""
    import sublime
    fname = file_name_for(lang)
    if fname is None:
        return None
    key = (kind, fname, code)
    if key in _cache:
        return _cache[key]
    import time
    t0 = time.perf_counter()
    result = None
    syntax = sublime.find_syntax_for_file(fname)
    if syntax is not None and syntax.scope != 'text.plain':
        p, scheme = _panel(window, kind)
        p.assign_syntax(syntax)
        p.run_command('mdgh_preview_panel_text', {'text': code})
        size = p.size()
        text = p.substr(sublime.Region(0, size))
        toks = []
        for region, scope in p.extract_tokens_with_scopes(sublime.Region(0, size)):
            toks.append((region.a, region.b) + _style(p, scheme, scope))
        fg = _style(p, scheme, 'text.plain')[0]
        result = tuple(assemble(text, toks, fg))
        _stats['panel_runs'] += 1
    _stats['ms'] += (time.perf_counter() - t0) * 1000
    if len(_cache) >= _CACHE_LIMIT:
        _cache.clear()
    _cache[key] = result
    return result


def stats():
    """Panel runs and ms spent since the last reset_stats (diagnostics)."""
    return dict(_stats)


def reset_stats():
    _stats.update(panel_runs=0, ms=0.0, style_calls=0, style_hits=0)


def close_window(window):
    entry = _panels.pop(window.id(), None)
    if entry is not None:
        window.destroy_output_panel(_PANEL_NAME)


def destroy_all():
    import sublime
    by_id = {w.id(): w for w in sublime.windows()}
    for wid in list(_panels):
        w = by_id.get(wid)
        if w is not None:
            w.destroy_output_panel(_PANEL_NAME)
    _panels.clear()
    _cache.clear()
    _styles.clear()
