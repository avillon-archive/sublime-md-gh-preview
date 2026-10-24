# -*- coding: utf-8 -*-
"""Hidden measurement panels (ST), measured inline layout (tables, ordered / task lists) and pure
toolbar/button placement arithmetic."""

PT_PER_PX = 0.75
BUTTON_MARGIN = 24

# ---------------------------------------------------------------- pure helpers


def choose_layout(line1_w, text_w, button_w, margin=BUTTON_MARGIN):
    """'A' when line 1 and the button share one display line, else 'B'.

    line1_w is the unwrapped width of line 1. Requiring room for the button as well makes
    the exact wrap point irrelevant: a line that fits with the button never wraps.
    """
    return 'A' if line1_w + button_w + margin <= text_w else 'B'


def fold_span(kind, size, anchor_line_end):
    """Region (a, b) that hides the source, or None when nothing is left to fold.

    'B' keeps only the first character. 'A' keeps the whole line holding the anchor, so a
    newline typed into line 1 (which pushes the anchor down a line) never folds the anchor.
    """
    if kind == 'B':
        return (1, size) if size > 1 else None
    a = anchor_line_end + 1
    return (a, size) if a < size else None


def edit_button_pad(text_w, x_end, button_w, margin=BUTTON_MARGIN):
    """Left padding for the edit-mode button placed at the end of line 1.

    Returns (pad, wraps). When the button does not fit after the last display line of
    line 1 it wraps onto a display line of its own, starting at x 0.
    """
    pad = text_w - x_end - button_w - margin
    if pad >= 0:
        return int(pad), False
    return max(0, int(text_w - button_w - margin)), True


def toolbar_b_pad(text_w, button_w, first_w, marker_w, margin=BUTTON_MARGIN):
    """Left padding for the preview button at point 0 (layout B): the first character and the
    fold marker are drawn to its right."""
    return max(0, int(text_w - button_w - first_w - marker_w - margin))


def first_diff(old, new):
    """First index where two block key sequences differ (len(new) when new extends old)."""
    n = min(len(old), len(new))
    for i in range(n):
        if old[i] != new[i]:
            return i
    return n


def text_area_width(viewport_w, em_w, word_wrap, wrap_width):
    """Width the text wraps at: the viewport, or wrap_width columns when that is narrower."""
    if word_wrap and wrap_width and wrap_width > 0 and em_w > 0:
        return min(viewport_w, wrap_width * em_w)
    return viewport_w


# ---------------------------------------------------------------- measured inline layout (pure)
#
# Width arithmetic for tables and ordered / task lists. Widths come from a measure function the
# caller passes in (ST panels at run time, fake widths in tests).

# Room left for the integer quantisation of measured widths: a column is forced SAFETY px wider
# than its widest measured line, and wrapped list text stops SAFETY px short of the edge.
SAFETY = 4
# Vertical cell borders per column plus the closing border of the last column.
CELL_BORDER = 1


def wrap_tokens(widths, kinds, maxw):
    """Greedy line breaking of measured tokens.

    kinds[i] is 'w' (a word or code span, never split), 's' (a space, dropped at line ends) or
    'n' (forced break). Returns the lines as lists of token indices. A line is wider than maxw only
    when it holds a single word."""
    lines = []
    cur = []
    w = 0.0

    def close():
        while cur and kinds[cur[-1]] == 's':
            cur.pop()
        lines.append(list(cur))

    for i, (tw, k) in enumerate(zip(widths, kinds)):
        if k == 'n':
            close()
            cur, w = [], 0.0
        elif k == 's':
            if cur:
                cur.append(i)
                w += tw
        else:
            if cur and w + tw > maxw:
                close()
                cur, w = [], 0.0
            cur.append(i)
            w += tw
    if cur or not lines:
        close()
    return lines


def table_budget(avail, ncol, cell_px):
    """Width left for the columns' text once paddings, borders and SAFETY are taken out."""
    return avail - ncol * (2 * cell_px + CELL_BORDER + SAFETY) - CELL_BORDER


def column_caps(nat, minw, budget):
    """Wrap width per column. nat: widest unwrapped cell, minw: widest single word.

    A table that fits keeps its natural widths. Otherwise every column is capped at the largest
    whole-px cap (bisection) whose total min(nat, cap) — never below the column's widest word —
    stays within budget. When even the widest words overflow, the columns get those."""
    if sum(nat) <= budget:
        return list(nat)

    def total(cap):
        return sum(max(m, min(n, cap)) for n, m in zip(nat, minw))
    lo, hi = 0, int(max(nat))
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if total(mid) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return [max(m, min(n, lo)) for n, m in zip(nat, minw)]


def align_pads(align, colw, linew):
    """(left, right) padding that places a line of linew in a column of colw."""
    extra = max(0, int(round(colw - linew)))
    if align == 'right':
        return extra, 0
    if align == 'center':
        return extra // 2, extra - extra // 2
    return 0, 0


def marker_pads(indent, marker_w, gap):
    """(left, right) padding of a list marker box that puts the item text at x = indent with the
    marker ending gap before it (the marker sits in the indent like a browser's outside marker)."""
    left = max(0, int(round(indent - gap - marker_w)))
    right = max(0, int(round(indent - left - marker_w)))
    return left, right


# ---------------------------------------------------------------- measurement panels (ST)

_PANEL_SETTINGS = {
    'word_wrap': False, 'gutter': False, 'line_numbers': False, 'margin': 0,
    'line_padding_top': 0, 'line_padding_bottom': 0, 'draw_white_space': 'none',
    'spell_check': False, 'is_widget': True, 'scroll_past_end': False,
}

# Font kinds of the measure function (see measurer).
FONT_KINDS = ('body', 'bold', 'mono')

_panels = {}    # (window_id, kind, font tuple) -> (view, name)
_widths = {}    # window_id -> {(kind, font tuple, text): width}
_WIDTHS_LIMIT = 50000    # per-window width cache entries
_serial = [0]
_stats = {'calls': 0, 'texts': 0, 'ms': 0.0}


def _font_key(font):
    return tuple(sorted(font.items()))


def _panel(window, kind, font):
    """Panel for one font (face and size). Fonts never change on an existing panel: re-measuring
    right after changing font_face on a panel returned bogus widths."""
    key = (window.id(), kind, _font_key(font))
    entry = _panels.get(key)
    if entry is not None:
        view, name = entry
        if view.is_valid():
            return view
        window.destroy_output_panel(name)
    _serial[0] += 1
    name = 'mdgh_measure_%s_%d' % (kind, _serial[0])
    view = window.create_output_panel(name, unlisted=True)
    s = view.settings()
    for k, v in _PANEL_SETTINGS.items():
        s.set(k, v)
    for k, v in font.items():
        s.set(k, v)
    view.set_scratch(True)
    _panels[key] = (view, name)
    return view


def css_font(face, px):
    """Panel font settings that match minihtml text of face at px CSS pixels."""
    return {'font_face': face, 'font_size': px * PT_PER_PX}


def line_height(window, kind, font):
    return float(_panel(window, kind, font).line_height())


def widths(window, kind, font, texts):
    """Rendered widths of single-line texts, cached per window. Uncached texts go into the panel
    in one batch, one per line."""
    cache = _widths.setdefault(window.id(), {})
    if len(cache) > _WIDTHS_LIMIT:
        cache.clear()   # before the need scan, so every text of this call is measured again
    fk = _font_key(font)
    need = sorted({t for t in texts if (kind, fk, t) not in cache})
    if need:
        import time
        t0 = time.perf_counter()
        p = _panel(window, kind, font)
        p.run_command('mdgh_preview_panel_text', {'text': '\n'.join(need)})
        for i, t in enumerate(need):
            a = p.text_point(i, 0)
            b = p.line(a).b
            cache[(kind, fk, t)] = p.text_to_layout(b)[0] - p.text_to_layout(a)[0]
        _stats['calls'] += 1
        _stats['texts'] += len(need)
        _stats['ms'] += (time.perf_counter() - t0) * 1000
    return [cache[(kind, fk, t)] for t in texts]


def measurer(window, body_face, mono_face):
    """measure(kind, px, texts) -> widths for the renderer. kind is one of FONT_KINDS; 'bold' is
    measured with the '<body face> Bold' font (a bold color scheme on a regular panel measures
    regular widths)."""
    faces = {'body': body_face, 'bold': body_face + ' Bold', 'mono': mono_face}

    def measure(kind, px, texts):
        return widths(window, kind, css_font(faces[kind], px), texts)
    return measure


def stats():
    """Panel batches, texts measured and ms spent since the last reset_stats (diagnostics)."""
    return dict(_stats)


def reset_stats():
    _stats.update(calls=0, texts=0, ms=0.0)


def clear_cache():
    """Drops every width and panel; the next measurement makes panels for the current fonts."""
    destroy_all()


def close_window(window):
    wid = window.id()
    for key in [k for k in _panels if k[0] == wid]:
        _view, name = _panels.pop(key)
        window.destroy_output_panel(name)
    _widths.pop(wid, None)


def destroy_all():
    import sublime
    by_id = {w.id(): w for w in sublime.windows()}
    for (wid, _kind, _fk), (_view, name) in list(_panels.items()):
        w = by_id.get(wid)
        if w is not None:
            w.destroy_output_panel(name)
    _panels.clear()
    _widths.clear()
