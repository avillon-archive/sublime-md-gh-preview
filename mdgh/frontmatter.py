# -*- coding: utf-8 -*-
"""The YAML subset of front matter that the preview shows as a table.

Pure: no YAML library. Read: top-level `key: scalar` (plain, single- or double-quoted), inline
lists `[a, b]` and block lists (`- x` lines under the key). A value outside the subset (nested
mapping, block scalar, flow mapping, multi-line plain scalar) is kept as its raw source lines.
"""
import re

_KEY = re.compile(r'''^("(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^\s#'"\[\]{},:&*!|>%@`-][^:#]*?|-[^\s:#][^:#]*?)'''
                  r''':(?:[ \t]+(.*))?$''')
_ITEM = re.compile(r'^([ \t]*)-(?:[ \t]+(.*))?$')
_COMMENT = re.compile(r'[ \t]+#.*$')
_ESCAPES = {'n': '\n', 't': '\t', '"': '"', '\\': '\\', '/': '/', '0': '\0', 'r': '\r'}


class Entry:
    """One top-level key. kind: 'scalar' (value: str), 'list' (value: [str]) or 'raw'
    (value: [str], the source lines of the value). rows: 0-based offsets inside the front
    matter content — key_row is the key's line; item_rows has one row per value item/line."""
    __slots__ = ('key', 'kind', 'value', 'key_row', 'item_rows')

    def __init__(self, key, kind, value, key_row, item_rows):
        self.key, self.kind, self.value = key, kind, value
        self.key_row, self.item_rows = key_row, item_rows

    def __repr__(self):
        return 'Entry(%r, %r, %r, %r, %r)' % (self.key, self.kind, self.value, self.key_row,
                                              self.item_rows)


def _unquote(s):
    """Value of a quoted scalar s (quotes included), or None when s is not one whole quoted string."""
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        body = s[1:-1]
        if re.search(r"(?<!')'(?!')", body.replace("''", '')):
            return None
        return body.replace("''", "'")
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        out = []
        i = 1
        while i < len(s) - 1:
            ch = s[i]
            if ch == '\\':
                if i + 1 >= len(s) - 1:
                    return None
                out.append(_ESCAPES.get(s[i + 1], s[i + 1]))
                i += 2
                continue
            if ch == '"':
                return None
            out.append(ch)
            i += 1
        return ''.join(out)
    return None


def _scalar(s):
    """A one-line scalar's text, or None when it is outside the subset."""
    s = s.strip()
    if not s or s[0] == '#':
        return ''
    if s[0] in '"\'':
        v = _unquote(s)
        return v if v is not None else _unquote(_COMMENT.sub('', s).rstrip())
    if s[0] in '[]{}&*!|>%@`' or s.startswith('- ') or s == '-':
        return None
    s = _COMMENT.sub('', s)
    if ': ' in s or s.endswith(':'):
        return None
    return s


def _split_flow(s):
    """Items of an inline list body (between the brackets), or None for nested flow values."""
    items = []
    cur = []
    quote = None
    for ch in s:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in '\'"':
            quote = ch
            cur.append(ch)
        elif ch in '[]{}':
            return None
        elif ch == ',':
            items.append(''.join(cur))
            cur = []
        else:
            cur.append(ch)
    if quote:
        return None
    last = ''.join(cur)
    if last.strip() or items:
        items.append(last)
    out = []
    for k, it in enumerate(items):
        if not it.strip():
            if k == len(items) - 1 and k:   # trailing comma
                continue
            return None
        v = _scalar(it)
        if v is None:
            return None
        out.append(v)
    return out


def _inline_list(s):
    s = s.strip()
    if not s.endswith(']'):
        s = _COMMENT.sub('', s).rstrip()
    if not (s.startswith('[') and s.endswith(']')):
        return None
    return _split_flow(s[1:-1])


def parse(content):
    """Entries of front matter text (without the --- fences), or None when it is not a top-level
    mapping this subset can read at all (then the caller shows it as a code block)."""
    lines = content.split('\n')
    entries = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip() or line.lstrip().startswith('#'):
            i += 1
            continue
        if line[0] in ' \t':
            return None          # indented text without a key above it
        m = _KEY.match(line.rstrip())
        if not m:
            return None
        key = m.group(1)
        if key[0] in '\'"':
            key = _unquote(key)
            if key is None:
                return None
        rest = m.group(2) or ''
        key_row = i
        # The value's continuation: indented lines, or `- ` items at column 0.
        j = i + 1
        body = []
        while j < n:
            ln = lines[j]
            if not ln.strip():
                body.append(j)
                j += 1
                continue
            if ln[0] in ' \t' or (not rest.strip() and _ITEM.match(ln) and ln[0] == '-'):
                body.append(j)
                j += 1
                continue
            break
        while body and not lines[body[-1]].strip():
            body.pop()
        j = body[-1] + 1 if body else i + 1
        entries.append(_entry(key, rest, key_row, body, lines))
        i = j
    return entries or None


def _entry(key, rest, key_row, body, lines):
    if rest.strip() and not body:
        v = _inline_list(rest) if rest.lstrip().startswith('[') else _scalar(rest)
        if v is not None:
            if isinstance(v, list):
                return Entry(key, 'list', v, key_row, [key_row] * len(v))
            return Entry(key, 'scalar', v, key_row, [key_row])
        return Entry(key, 'raw', [rest.strip()], key_row, [key_row])
    if not rest.strip() and body:
        items = []
        rows = []
        indent = None
        for r in body:
            ln = lines[r]
            if not ln.strip() or ln.lstrip().startswith('#'):
                continue
            m = _ITEM.match(ln)
            if not m or (indent is not None and m.group(1) != indent):
                items = None
                break
            indent = m.group(1)
            v = _scalar(m.group(2) or '')
            if v is None:
                items = None
                break
            items.append(v)
            rows.append(r)
        if items:
            return Entry(key, 'list', items, key_row, rows)
    if not rest.strip() and not body:
        return Entry(key, 'scalar', '', key_row, [key_row])
    # Outside the subset: the value's source lines as they are.
    raw = ([rest.strip()] if rest.strip() else []) + [lines[r] for r in body]
    rows = ([key_row] if rest.strip() else []) + body
    return Entry(key, 'raw', raw, key_row, rows)
