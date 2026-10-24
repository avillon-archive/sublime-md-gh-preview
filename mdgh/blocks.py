# -*- coding: utf-8 -*-
"""Markdown parsing and top-level block splitting."""
import hashlib
import re
import unicodedata
from dataclasses import dataclass

from markdown_it import MarkdownIt
from mdit_py_plugins.gfm import gfm_plugin

NEWLINES = re.compile(r'\r\n?|\n')
_COMMENT = re.compile(r'<!--.*?(?:-->|\Z)', re.S)
_DETAILS_CLOSE = re.compile(r'</details\s*>', re.I)

_KIND = {
    'heading_open': 'heading',
    'paragraph_open': 'paragraph',
    'bullet_list_open': 'bullet_list',
    'ordered_list_open': 'ordered_list',
    'blockquote_open': 'blockquote',
    'hr': 'hr',
    'fence': 'fence',
    'code_block': 'code_block',
    'html_block': 'html_block',
    'front_matter': 'front_matter',
    'table_open': 'table',
    'footnote_block_open': 'footnotes',
    'alert_open': 'alert',
}

_md = None


def _parser():
    # Created on first use so importing this module stays cheap.
    global _md
    if _md is None:
        _md = MarkdownIt('commonmark').use(gfm_plugin, front_matter=True)
    return _md


@dataclass(frozen=True)
class Block:
    index: int
    kind: str
    start: int
    end: int
    map_start: int
    map_end: int
    tokens: tuple
    src: str
    key: str
    slug: 'str | None'
    # `key` ignores position so it can match a block after lines were inserted above it;
    # the rendered html embeds absolute row numbers, so html caches must use this one.
    html_key: str = ''


@dataclass
class Document:
    blocks: list
    line_count: int
    env: dict


def is_comment_only(content):
    """True when an HTML fragment is nothing but comments (an unclosed one runs to the end)."""
    return not _COMMENT.sub('', content).strip()


def is_hidden_html(content):
    """True when an HTML block draws nothing: only comments and </details> closing tags (the
    preview's details are always open, so their end needs no mark)."""
    return not _DETAILS_CLOSE.sub('', _COMMENT.sub('', content)).strip()


def _top_level(tokens):
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        j = i
        if t.nesting == 1:
            depth = 0
            for j in range(i, n):
                depth += tokens[j].nesting
                if depth == 0:
                    break
        yield t, tuple(tokens[i:j + 1])
        i = j + 1


def _sha1(*parts):
    h = hashlib.sha1()
    for p in parts:
        h.update(p.encode('utf-8', 'surrogatepass'))
        h.update(b'\0')
    return h.hexdigest()


def _heading_text(inline):
    out = []
    for c in inline.children or ():
        if c.type in ('text', 'code_inline', 'image'):
            out.append(c.content)
        elif c.type in ('softbreak', 'hardbreak'):
            out.append(' ')
    return ''.join(out)


def _footnote_ids(tokens):
    ids = []
    for t in tokens:
        for c in t.children or ():
            if c.type == 'footnote_ref':
                ids.append(str(c.meta['id']))
    return ','.join(ids)


def slugify(text, seen):
    """GitHub heading anchor: lowercase, drop non-word chars, spaces to '-', -1/-2 suffix on repeats."""
    kept = []
    for ch in text.lower():
        cat = unicodedata.category(ch)
        if ch in ' -_' or cat[0] in 'LM' or cat in ('Nd', 'Nl', 'Pc'):
            kept.append(ch)
    base = ''.join(kept).replace(' ', '-')
    n = seen.get(base)
    if n is None:
        seen[base] = 0
        return base
    while True:
        n += 1
        cand = '%s-%d' % (base, n)
        if cand not in seen:
            break
    seen[base] = n
    seen[cand] = 0
    return cand


def parse(text):
    lines = NEWLINES.split(text) if text else []
    line_count = len(lines)
    env = {}
    tokens = _parser().parse(text, env)

    entries = []
    footnotes = None
    seen = {}
    for t, toks in _top_level(tokens):
        kind = _KIND.get(t.type)
        if kind is None:
            continue
        if kind == 'html_block' and is_hidden_html(t.content):
            continue
        if kind == 'footnotes':
            footnotes = toks
            continue
        slug = slugify(_heading_text(toks[1]), seen) if kind == 'heading' else None
        entries.append((kind, toks, t.map[0], t.map[1], slug))

    blocks = []
    for k, (kind, toks, ms, me, slug) in enumerate(entries):
        start = 0 if k == 0 else ms
        end = entries[k + 1][2] if k + 1 < len(entries) else line_count
        src = '\n'.join(lines[ms:me])
        key = _sha1(src, _footnote_ids(toks))
        blocks.append(Block(len(blocks), kind, start, end, ms, me, toks, src, key, slug,
                            _sha1(key, str(ms))))
    if footnotes is not None:
        # One block per footnote, so a #fn-<n> link lands on the note's own block top; the
        # first and last flags are in the key because they change the block's wrapper.
        items = _footnote_items(footnotes)
        for k, item in enumerate(items):
            start = 0 if not blocks else line_count
            toks = (footnotes[0],) + item + (footnotes[-1],)
            key = _sha1(*[t.content + repr(t.meta.get('id')) + str(t.meta.get('label'))
                          for t in item], 'first' if k == 0 else '',
                        'last' if k == len(items) - 1 else '')
            rows = ','.join(str(t.map[0]) for t in item if t.map)
            blocks.append(Block(len(blocks), 'footnotes', start, line_count, start, start, toks,
                                '', key, None, _sha1(key, rows)))
    return Document(blocks, line_count, env)


def _footnote_items(footnotes):
    """footnote_open..footnote_close token runs of a footnote_block (its open/close excluded)."""
    items = []
    cur = None
    depth = 0
    for t in footnotes[1:-1]:
        if t.type == 'footnote_open' and depth == 0:
            cur = [t]
            depth = 1
            continue
        if cur is None:
            continue
        cur.append(t)
        if t.type == 'footnote_open':
            depth += 1
        elif t.type == 'footnote_close':
            depth -= 1
            if depth == 0:
                items.append(tuple(cur))
                cur = None
    return items


def heading_text(block):
    """Plain text of a heading block (the Goto Symbol list)."""
    return _heading_text(block.tokens[1])


def headings(doc):
    """(block index, level 1-6, text) of every heading block, in document order."""
    return [(b.index, int(b.tokens[0].tag[1:]), heading_text(b))
            for b in doc.blocks if b.kind == 'heading']


def footnote_blocks(doc):
    """({n: block of note n}, {n: first block referencing note n}); n is the 1-based number."""
    notes = {}
    refs = {}
    for b in doc.blocks:
        if b.kind == 'footnotes':
            for t in b.tokens:
                if t.type == 'footnote_open':
                    notes.setdefault(t.meta['id'] + 1, b.index)
        for t in b.tokens:
            for c in t.children or ():
                if c.type == 'footnote_ref':
                    refs.setdefault(c.meta['id'] + 1, b.index)
    return notes, refs
