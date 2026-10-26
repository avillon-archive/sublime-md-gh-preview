# -*- coding: utf-8 -*-
"""Markdown-it tokens to minihtml phantom markup."""
import html
import re
from dataclasses import dataclass

from . import frontmatter, layout, navigation, theme
from .blocks import Block, Document, is_comment_only

EDIT_HREF_PREFIX = 'mdgh:e:'
# Footnote links (n = 1-based footnote number): reference -> note, note -> reference.
FOOTNOTE_HREF = '#fn-%d'
FOOTNOTE_BACK_HREF = '#fnref-%d'

ALLOWED_TAGS = frozenset({
    'body', 'div', 'span', 'a', 'b', 'i', 'code', 'br', 'p', 'ul', 'li', 'img',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
})
ALLOWED_CSS_PROPS = frozenset({
    'padding', 'padding-left', 'padding-right', 'padding-top', 'padding-bottom',
    'margin', 'margin-left', 'margin-right', 'margin-top', 'margin-bottom',
    'display', 'width', 'height', 'white-space', 'text-align', 'line-height',
    'position', 'top', 'bottom', 'left', 'right',
    'color', 'background-color', 'font-size', 'font-weight', 'font-style',
    'border', 'border-top', 'border-bottom', 'border-left', 'border-right', 'border-radius',
})

_MULTI_SPACE = re.compile(' {2,}')
_WORDS = re.compile(r'[^ \t]+|[ \t]+')   # no-break spaces stay inside words
_ALERT_CLASS = {'NOTE': 'note', 'TIP': 'tip', 'IMPORTANT': 'important', 'WARNING': 'warning',
                'CAUTION': 'caution'}

# Transparent 1x1 PNG stretched to a column's width: minihtml has no width for inline-blocks.
SPACER_SRC = 'res://' + theme.resource_path('icons/spacer.png')
# Zero-width code-font run at the start of every table line, so a line with a code span has the
# same line box as one without (otherwise cells sit 1px apart and borders step). The second,
# body-font zero-width space gives a line holding only code-font text (a code span, a kbd box,
# raw front matter) the body line height: cells are inline-blocks on one baseline, so a shorter
# cell would sit lower than its neighbours.
STRUT = '<span class="strut">\u200b</span>\u200b'
# 1px-font space after a code span or kbd box with a word glued to its end. minihtml draws the
# box once the span fits on the line and leaves it there when the glued tail then moves the whole
# word to the next line; this space lets the tail wrap alone. U+200B is no break point there.
CODE_BREAK = '<span class="cb"> </span>'
# Body-font zero-width space in front of a code span or kbd box in flowing text: minihtml never
# breaks a line at it, so a wrapped line holding only the box still gets the body line height
# instead of the shorter code-font one (the same job as the second half of STRUT).
CODE_LEAD = '​'
BACKREF_TEXT = '\u21a9'

# Raw HTML tags the preview renders; any other tag stays escaped source text. details is always
# open: its summary is a title line with this marker, its content blocks follow as usual.
HTML_SUBSET = frozenset({'br', 'kbd', 'sub', 'sup', 'img', 'details', 'summary'})
_HTML_INLINE_SPANS = {'kbd': (CODE_LEAD + '<code class="kbd">', '</code>'),
                      'sub': ('<span class="sub">', '</span>'),
                      'sup': ('<span class="sup">', '</span>')}
SUMMARY_MARKER = '\u25be'
DEFAULT_SUMMARY = 'Details'
_HTML_PIECE = re.compile(
    r'<!--.*?(?:-->|\Z)'
    r'|<(/?)([A-Za-z][A-Za-z0-9-]*)'
    r'''((?:\s+[^\s"'>/=]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?)*)\s*(/?)>''', re.S)
_HTML_ATTR = re.compile(r'''([^\s"'>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?''')


def html_pieces(s):
    """Raw HTML split into ('text', s), ('comment', s) and ('tag', name, closing, attrs, raw)
    pieces (name lowercased, attribute values unescaped). Anything that is not a well-formed tag
    or comment is text, so unbalanced or broken markup never raises."""
    out = []
    pos = 0
    for m in _HTML_PIECE.finditer(s):
        if m.start() > pos:
            out.append(('text', s[pos:m.start()]))
        raw = m.group(0)
        if raw.startswith('<!--'):
            out.append(('comment', raw))
        else:
            attrs = {}
            for a in _HTML_ATTR.finditer(m.group(3) or ''):
                v = next((g for g in a.groups()[1:] if g is not None), '')
                attrs.setdefault(a.group(1).lower(), html.unescape(v))
            out.append(('tag', m.group(2).lower(), bool(m.group(1)), attrs, raw))
        pos = m.end()
    if pos < len(s):
        out.append(('text', s[pos:]))
    return out


def _glued(children, i):
    """Whether the flowing text after children[i] goes on with no space in between."""
    for c in children[i + 1:]:
        ty = c.type
        if ty in ('softbreak', 'hardbreak'):
            return False
        if ty in ('text', 'code_inline'):
            if c.content:
                return c.content[0] not in ' \t'
        elif ty == 'html_inline':
            if not is_comment_only(c.content):
                tag = _single_tag(c.content)
                return tag is None or tag[1] != 'br'
        elif ty in ('image', 'footnote_ref'):
            return True
    return False


def _single_tag(content):
    """The tag piece when an html_inline token is one subset tag, else None."""
    p = html_pieces(content)
    if len(p) == 1 and p[0][0] == 'tag' and p[0][1] in HTML_SUBSET:
        return p[0]
    return None


def remote_urls(block):
    """http(s) image URLs a block shows (Markdown images and raw HTML <img>), in order."""
    urls = []

    def add(src):
        src = (src or '').strip()
        if navigation.image_source('', src)[0] == 'remote' and src not in urls:
            urls.append(src)

    def html_srcs(content):
        for p in html_pieces(content):
            if p[0] == 'tag' and p[1] == 'img' and not p[2]:
                add(p[3].get('src'))

    for t in block.tokens:
        if t.type == 'html_block':
            html_srcs(t.content)
        for c in t.children or ():
            if c.type == 'image':
                add(c.attrGet('src'))
            elif c.type == 'html_inline':
                html_srcs(c.content)
    return tuple(urls)


@dataclass(frozen=True)
class RenderContext:
    body_px: float
    pad_left: int
    pad_right: int
    theme: str
    avail: int = 0          # px inside the block wrapper's paddings (tables, list wrapping)
    metrics: tuple = ()     # theme.layout_metrics(vars, body_px)
    fonts: tuple = ()       # (body face, mono face) the measure function measures with
    doc_dir: str = ''       # folder of the document file ('' = unsaved): relative image paths

    def key(self):
        return (round(self.body_px, 3), self.pad_left, self.pad_right, self.theme, self.avail,
                self.metrics, self.fonts, self.doc_dir)


def block_pads(phantom_w, min_pad, max_content):
    """(pad_left, pad_right, avail) of a block wrapper in a block phantom phantom_w wide.

    The content is at most max_content wide (<= 0: no limit) and centred; it always keeps
    min_pad on both sides (GitHub's markdown-body side padding)."""
    phantom_w = int(phantom_w)
    min_pad = int(min_pad)
    inner = max(0, phantom_w - 2 * min_pad)
    max_content = int(round(max_content))
    if max_content <= 0 or inner <= max_content:
        return min_pad, min_pad, inner
    extra = phantom_w - max_content
    left = extra // 2
    return left, extra - left, max_content


def _roman(n):
    out = []
    for value, digits in ((1000, 'm'), (900, 'cm'), (500, 'd'), (400, 'cd'), (100, 'c'),
                          (90, 'xc'), (50, 'l'), (40, 'xl'), (10, 'x'), (9, 'ix'), (5, 'v'),
                          (4, 'iv'), (1, 'i')):
        while n >= value:
            out.append(digits)
            n -= value
    return ''.join(out)


def _alpha(n):
    out = ''
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(ord('a') + r) + out
    return out


def list_marker(n, depth):
    """Ordered list marker of item number n at list nesting depth (0 = top level), as GitHub
    styles it: decimal, then lower-roman inside one list, lower-alpha deeper. CSS falls back to
    decimal for numbers a style cannot spell (roman outside 1-3999, alpha below 1)."""
    if depth == 1 and 1 <= n <= 3999:
        return _roman(n) + '.'
    if depth >= 2 and n >= 1:
        return _alpha(n) + '.'
    return '%d.' % n


def _esc(s):
    return html.escape(s, quote=False)


def _keep_spaces(s):
    # Runs of spaces collapse in minihtml; all but the last become no-break spaces so
    # the run keeps its width and the line can still wrap after it.
    return _MULTI_SPACE.sub(lambda m: '&nbsp;' * (len(m.group(0)) - 1) + ' ', s)


def _split_level(tokens):
    """Pairs (token, inner tokens or None) for the sibling nodes of one nesting level."""
    out = []
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t.nesting == 1:
            depth = 0
            j = i
            for j in range(i, n):
                depth += tokens[j].nesting
                if depth == 0:
                    break
            out.append((t, tokens[i + 1:j]))
            i = j + 1
        else:
            out.append((t, None))
            i += 1
    return out


def _wrap(cls, inner, ctx):
    return ('<body id="mdgh"><div class="%s" style="padding-left:%dpx;padding-right:%dpx">%s</div></body>'
            % (cls, ctx.pad_left, ctx.pad_right, inner))


def _link(href, inner):
    h = html.escape(href, quote=True)
    return '<a href="%s" title="%s">%s</a>' % (h, h, inner)


def _footnote_ref(n):
    return '<span class="fnref">%s</span>' % _link(FOOTNOTE_HREF % n, '[%d]' % n)


def _backref(n):
    return _link(FOOTNOTE_BACK_HREF % n, BACKREF_TEXT)


def _anchor_id(inner):
    """Footnote id of the first footnote_anchor in a paragraph's tokens, or None."""
    for t in inner or ():
        if t.type == 'footnote_anchor':
            return t.meta['id']
    return None


# ---------------------------------------------------------------- measured inline tokens


class _Style:
    """Formatting shared by consecutive tokens of one emitted segment."""
    __slots__ = ('bold', 'italic', 'strike', 'code', 'href', 'cls', 'row')

    def __init__(self, bold, italic, strike, code, href, cls, row):
        self.bold, self.italic, self.strike, self.code = bold, italic, strike, code
        self.href, self.cls, self.row = href, cls, row

    def _t(self):
        return (self.bold, self.italic, self.strike, self.code, self.href, self.cls, self.row)

    def __eq__(self, other):
        return isinstance(other, _Style) and self._t() == other._t()

    def __hash__(self):
        return hash(self._t())


class _Tok:
    """One unit of measured layout: a word, a space, a code span or a forced break."""
    __slots__ = ('text', 'kind', 'font', 'px', 'style')

    def __init__(self, text, kind, font, px, style):
        self.text, self.kind, self.font, self.px, self.style = text, kind, font, px, style

    def key(self):
        return (self.font, self.px, self.text)


class _Meter:
    """Widths of (font kind, px, text) gathered in batches: one measure call per font and size."""

    def __init__(self, measure):
        self.measure = measure
        self.w = {}

    def fill(self, keys):
        groups = {}
        for k in keys:
            if k not in self.w:
                groups.setdefault(k[:2], set()).add(k[2])
        for (font, px), texts in groups.items():
            texts = sorted(texts)
            for t, w in zip(texts, self.measure(font, px, texts)):
                self.w[(font, px, t)] = w

    def get(self, key):
        return self.w[key]


class _Renderer:
    def __init__(self, doc, ctx, measure, highlight=None, image_size=None, block=None,
                 remote=None):
        self.highlight = highlight
        self.image_size = image_size or navigation.read_image_size
        self.remote = remote
        self.block = block
        self.tail_summary = False    # the last html node rendered ended with a <summary> line
        self.depth = 0           # list nesting depth (ordered list marker style)
        self.doc = doc
        self.ctx = ctx
        self.m = dict(ctx.metrics)
        self.meter = _Meter(measure)

    # ---- inline (flowing text)

    def _run(self, text, row, link, fix=None):
        if not text:
            return ''
        s = _esc(text)
        if fix:
            s = fix(s)
        if link or row is None or not text.strip():
            return s
        return '<a class="e" href="%s%d">%s</a>' % (EDIT_HREF_PREFIX, row, s)

    def image(self, c, row, link, max_w):
        """minihtml of an image token: the picture for a readable local PNG/JPG/GIF, a link
        with the alt text for a remote one, the alt text otherwise."""
        return self._image_html(c.attrGet('src') or '', c.content or '[image]', row, link, max_w)

    def _image_html(self, src, alt, row, link, max_w, attrs=None):
        kind, target = self._source(src)
        if kind == 'local':
            img = self._img(target, max_w, attrs)
            if img is not None:
                if link or row is None:
                    return img
                return '<a class="e" href="%s%d">%s</a>' % (EDIT_HREF_PREFIX, row, img)
        if kind == 'remote' and not link:
            return _link(src.strip(), _esc(alt))
        return self._run(alt, row, link)

    def _source(self, src):
        """navigation.image_source, with a remote image that is in the download cache as a
        local file (only when remote images are on: self.remote)."""
        kind, target = navigation.image_source(self.ctx.doc_dir, src)
        if kind == 'remote' and self.remote is not None:
            path = self.remote(target)
            if path:
                return 'local', path
        return kind, target

    def _img_size(self, path, max_w, attrs=None):
        size = self.image_size(path)
        if not size:
            return None
        if attrs:
            return navigation.attr_image_size(size[0], size[1], attrs.get('width'),
                                              attrs.get('height'), max_w)
        return navigation.fit_image(size[0], size[1], max_w)

    def _img(self, path, max_w, attrs=None):
        size = self._img_size(path, max_w, attrs)
        if size is None:
            return None
        w, h = size
        # minihtml draws an image 2px taller on a line with a line-height; the .im span's own
        # line-height keeps it at its size.
        return '<span class="im"><img src="%s" width="%d" height="%d"></span>' % (
            html.escape(navigation.file_src(path), quote=True), w, h)

    def inline(self, children, row, suffix='', w=None):
        out = []
        link = 0
        stack = []
        w = self.ctx.avail if w is None else w
        children = children or ()
        for i, c in enumerate(children):
            ty = c.type
            if ty == 'text':
                out.append(self._run(c.content, row, link))
            elif ty == 'softbreak':
                out.append(' ')
                row = None if row is None else row + 1
            elif ty == 'hardbreak':
                out.append('<br>')
                row = None if row is None else row + 1
            elif ty == 'code_inline':
                out.append('%s<code>%s</code>' % (CODE_LEAD, self._run(c.content, row, link,
                                                                       _keep_spaces)))
                if _glued(children, i):
                    out.append(CODE_BREAK)
            elif ty == 'strong_open':
                out.append('<b>')
            elif ty == 'strong_close':
                out.append('</b>')
            elif ty == 'em_open':
                out.append('<i>')
            elif ty == 'em_close':
                out.append('</i>')
            elif ty == 's_open':
                out.append('<span class="del"><span class="del2">')
            elif ty == 's_close':
                out.append('</span></span>')
            elif ty == 'link_open':
                href = html.escape(c.attrGet('href') or '', quote=True)
                out.append('<a href="%s" title="%s">' % (href, href))
                link += 1
            elif ty == 'link_close':
                out.append('</a>')
                link -= 1
            elif ty == 'image':
                out.append(self.image(c, row, link, w))
            elif ty == 'footnote_ref':
                out.append(_footnote_ref(c.meta['id'] + 1))
            elif ty == 'html_inline':
                if not is_comment_only(c.content):
                    tag = _single_tag(c.content)
                    s = (self._run(c.content, row, link) if tag is None
                         else self.html_tag(tag, row, link, w, stack))
                    out.append(s)
                    if s.endswith('</code>') and _glued(children, i):   # a kbd box closed
                        out.append(CODE_BREAK)
                if row is not None:
                    row += c.content.count('\n')
            else:
                out.append(self._run(c.content, row, link))
        out.extend(_HTML_INLINE_SPANS[name][1] for name in reversed(stack))
        if suffix:
            out.append(suffix)
        return ''.join(out)

    def html_tag(self, tag, row, link, w, stack):
        """minihtml of one subset tag in flowing text. stack: names of the kbd/sub/sup elements
        open in this run of text; a closing tag closes up to its own element (an unmatched one
        is dropped), the caller closes what is left."""
        _, name, closing, attrs, raw = tag
        if name == 'br':
            return '<br>'
        if name == 'img':
            if closing:
                return ''
            return self._image_html(attrs.get('src') or '', attrs.get('alt') or '[image]', row,
                                    link, w, attrs)
        if name not in _HTML_INLINE_SPANS:
            return self._run(raw, row, link)     # details / summary inside a paragraph
        if not closing:
            stack.append(name)
            return _HTML_INLINE_SPANS[name][0]
        if name not in stack:
            return ''
        out = []
        while stack:
            top = stack.pop()
            out.append(_HTML_INLINE_SPANS[top][1])
            if top == name:
                break
        return ''.join(out)

    def _inline_node(self, inline_tok, suffix='', w=None):
        row = inline_tok.map[0] if inline_tok.map else None
        return self.inline(inline_tok.children, row, suffix, w)

    # ---- inline (measured tokens: table cells, list item text)

    def tokens(self, children, row, px, bold=False, img_w=0):
        """Measured-layout tokens of an inline token's children (same rows as inline()).
        A shown image is one 'img' token (text = its <img>, px = its width) of at most img_w."""
        toks = []
        b = i = s = 0
        href = None
        spans = []      # open raw HTML kbd/sub/sup elements, innermost last

        def style(code=False, cls=None, link=None):
            return _Style(bool(b) or bold, bool(i), bool(s), code, link or href, cls, row)

        def text(t):
            inner = spans[-1] if spans else None
            if inner == 'kbd':
                if t:
                    toks.append(_Tok(t, 'w', 'mono', self.m['code'], style(code='kbd')))
                return
            st = style(cls=inner)
            font = 'bold' if st.bold else 'body'
            self.word_tokens(toks, t, font, self.m['sup'] if inner else px, st)

        def image(src, alt, attrs):
            nonlocal href
            kind, target = self._source(src)
            size = self._img_size(target, img_w, attrs) if kind == 'local' else None
            if size is not None:
                toks.append(_Tok(self._img(target, img_w, attrs), 'img', 'img', float(size[0]),
                                 style()))
            elif kind == 'remote' and href is None:
                href = src.strip()
                text(alt)
                href = None
            else:
                text(alt)

        for c in children or ():
            ty = c.type
            if ty == 'softbreak':
                toks.append(_Tok(' ', 's', 'bold' if (b or bold) else 'body', px, style()))
                row = None if row is None else row + 1
            elif ty == 'hardbreak':
                toks.append(_Tok('', 'n', 'body', px, style()))
                row = None if row is None else row + 1
            elif ty == 'code_inline':
                toks.append(_Tok(c.content, 'w', 'mono', self.m['code'], style(code=True)))
            elif ty == 'strong_open':
                b += 1
            elif ty == 'strong_close':
                b -= 1
            elif ty == 'em_open':
                i += 1
            elif ty == 'em_close':
                i -= 1
            elif ty == 's_open':
                s += 1
            elif ty == 's_close':
                s -= 1
            elif ty == 'link_open':
                href = c.attrGet('href') or ''
            elif ty == 'link_close':
                href = None
            elif ty == 'image':
                image(c.attrGet('src') or '', c.content or '[image]', None)
            elif ty == 'footnote_ref':
                n = c.meta['id'] + 1
                toks.append(_Tok('[%d]' % n, 'w', 'body', self.m['sup'],
                                 style(cls='fnref', link=FOOTNOTE_HREF % n)))
            elif ty == 'html_inline':
                if not is_comment_only(c.content):
                    tag = _single_tag(c.content)
                    name = tag[1] if tag else None
                    if name == 'br':
                        toks.append(_Tok('', 'n', 'body', px, style()))
                    elif name == 'img':
                        if not tag[2]:
                            image(tag[3].get('src') or '', tag[3].get('alt') or '[image]', tag[3])
                    elif name in _HTML_INLINE_SPANS:
                        if not tag[2]:
                            spans.append(name)
                        elif name in spans:
                            del spans[len(spans) - 1 - spans[::-1].index(name):]
                    else:
                        text(c.content)
                if row is not None:
                    row += c.content.count('\n')
            elif c.content:
                text(c.content)
        return toks

    @staticmethod
    def word_tokens(toks, t, font, px, st):
        """Appends the word and space tokens of text t (one style) to toks."""
        for m in _WORDS.finditer(t):
            w = m.group(0)
            if w[0] in ' \t':
                toks.append(_Tok(' ', 's', font, px, st))
            else:
                toks.append(_Tok(w, 'w', font, px, st))

    def backref_tokens(self, n, px):
        st = _Style(False, False, False, False, FOOTNOTE_BACK_HREF % n, None, None)
        return [_Tok(' ', 's', 'body', px, st), _Tok(BACKREF_TEXT, 'w', 'body', px, st)]

    @staticmethod
    def measured_keys(toks):
        """Meter keys of the tokens that are measured text."""
        return [t.key() for t in toks if t.kind not in ('n', 'img')]

    @staticmethod
    def kinds(toks):
        """layout.wrap_tokens kinds: an image is an unbreakable word."""
        return ['w' if t.kind == 'img' else t.kind for t in toks]

    def tok_width(self, t):
        if t.kind == 'n':
            return 0.0
        if t.kind == 'img':
            return t.px
        w = self.meter.get(t.key())
        if t.style.code:
            w += 2 * self.m['code_px']
            if t.style.code == 'kbd':
                w += 2      # the kbd box's 1px side borders
        return w

    @staticmethod
    def run_keys(line):
        """(font, px, text) of the same-font runs of a laid-out line; code spans stand alone."""
        keys = []
        cur = None
        for t in line:
            if t.style.code or t.kind == 'img':
                cur = None
                keys.append(None)
                continue
            k = (t.font, t.px)
            if cur is not None and cur[:2] == k:
                cur = (k[0], k[1], cur[2] + t.text)
                keys[-1] = cur
            else:
                cur = (k[0], k[1], t.text)
                keys.append(cur)
        return [k for k in keys if k is not None]

    def line_width(self, line):
        """Width of a laid-out line measured run by run (not summed token by token, so integer
        rounding does not accumulate over a long line)."""
        w = sum(self.meter.get(k) for k in self.run_keys(line))
        return w + sum(self.tok_width(t) for t in line if t.style.code or t.kind == 'img')

    def wrap(self, toks, maxw):
        lines = layout.wrap_tokens([self.tok_width(t) for t in toks], self.kinds(toks), maxw)
        return [[toks[i] for i in line] for line in lines]

    @staticmethod
    def emit(line):
        """minihtml of a laid-out line: one segment per run of equal style."""
        out = []
        k = 0
        n = len(line)
        while k < n:
            st = line[k].style
            if line[k].kind == 'img':
                s = line[k].text
                k += 1
                if st.href is not None:
                    s = _link(st.href, s)
                elif st.row is not None:
                    s = '<a class="e" href="%s%d">%s</a>' % (EDIT_HREF_PREFIX, st.row, s)
                out.append(s)
                continue
            j = k
            while j < n and line[j].style == st and line[j].kind != 'img':
                j += 1
                if st.code == 'kbd':
                    break       # one box per kbd element
            text = ''.join(t.text for t in line[k:j])
            k = j
            s = _esc(text)
            if st.code:
                s = s.replace(' ', '&nbsp;')
            if st.href is None and st.row is not None and text.strip():
                s = '<a class="e" href="%s%d">%s</a>' % (EDIT_HREF_PREFIX, st.row, s)
            if st.code:
                s = '<code%s>%s</code>' % (' class="kbd"' if st.code == 'kbd' else '', s)
            if st.strike:
                s = '<span class="del"><span class="del2">%s</span></span>' % s
            if st.italic:
                s = '<i>%s</i>' % s
            if st.bold:
                s = '<b>%s</b>' % s
            if st.href is not None:
                s = _link(st.href, s)
            if st.cls:
                s = '<span class="%s">%s</span>' % (st.cls, s)
            out.append(s)
        return ''.join(out)

    # ---- block containers

    @staticmethod
    def _join(items):
        """items: (html, tight) pairs; every block but the last gets the 16px gap below it."""
        items = [(h, tight) for h, tight in items if h]
        out = []
        for k, (h, tight) in enumerate(items):
            last = k == len(items) - 1
            out.append(h if last or tight else '<div class="g">%s</div>' % h)
        return ''.join(out)

    def nodes(self, nodes, ul, w, px):
        return self._join([self.node(t, inner, ul, w, px) for t, inner in nodes])

    def node(self, t, inner, ul, w, px):
        """Returns (html, tight): tight marks a hidden paragraph, which needs no gap below.
        w: width available to this node's content, px: its text size."""
        ty = t.type
        if ty == 'heading_open':
            return '<%s>%s</%s>' % (t.tag, self._inline_node(inner[0], '', w), t.tag), False
        if ty == 'paragraph_open':
            fn = _anchor_id(inner)
            suffix = ' ' + _backref(fn + 1) if fn is not None else ''
            content = self._inline_node(inner[0], suffix, w) if inner else ''
            if t.hidden:
                return content, True
            return '<p>%s</p>' % content, False
        if ty in ('bullet_list_open', 'ordered_list_open'):
            return self.list(t, inner, ul, w, px), False
        quote = self.m['bar'] + 2 * self.m['quote_pad']
        if ty == 'blockquote_open':
            return ('<div class="bq">%s</div>'
                    % self.nodes(_split_level(inner), ul, w - quote, px)), False
        if ty == 'alert_open':
            return self.alert(t, inner, ul, w - quote, px), False
        if ty == 'table_open':
            return self.table(inner, w, px), False
        if ty == 'footnote_block_open':
            return self.footnotes(inner, ul, w), False
        if ty == 'hr':
            return '<div class="hr">&nbsp;</div>', False
        if ty == 'fence':
            return self.code(t.content, t.map[0] + 1, t.info), False
        if ty == 'front_matter':
            return self.front_matter(t, w, px), False
        if ty == 'code_block':
            return self.code(t.content, t.map[0]), False
        if ty == 'html_block':
            if is_comment_only(t.content):
                return '', False
            return self.html_block(t, w)
        if inner:
            return self.nodes(_split_level(inner), ul, w, px), False
        return '', False

    # ---- leaves

    def code(self, content, first_row, info=None):
        if content.endswith('\n'):
            content = content[:-1]
        lines = content.split('\n')
        hl = self.highlight(info, content) if self.highlight and info else None
        if hl is not None and len(hl) != len(lines):
            hl = None
        out = []
        for k, line in enumerate(lines):
            body = (hl[k] if hl is not None else _esc(line)) or ' '
            out.append('<a class="e" href="%s%d">%s</a>' % (EDIT_HREF_PREFIX, first_row + k, body))
        return '<div class="pre">%s</div>' % '\n'.join(out)

    def table(self, inner, w, px):
        rows = []       # (header, [(align, toks)])
        img_w = layout.table_budget(w, 1, self.m['cell_px'])
        cells = None
        row = None
        header = False
        align = 'left'
        for t in inner:
            if t.type == 'tr_open':
                cells = []
                row = t.map[0] if t.map else None
            elif t.type in ('th_open', 'td_open'):
                header = t.type == 'th_open'
                m = re.search(r'text-align:\s*(left|right|center)', t.attrGet('style') or '')
                align = m.group(1) if m else 'left'
            elif t.type == 'inline':
                cells.append((align, self.tokens(t.children, row, px, bold=header, img_w=img_w)))
            elif t.type == 'tr_close':
                rows.append((header, cells))
        return self.grid(rows, w)

    def grid(self, rows, w):
        """minihtml of a table. rows: (header, [(align, measured tokens)]) per row."""
        if not rows:
            return ''
        ncol = max(len(c) for _, c in rows)
        for _, c in rows:
            c.extend([('left', [])] * (ncol - len(c)))
        self.meter.fill(k for _, c in rows for _, toks in c for k in self.measured_keys(toks))

        nat = [0.0] * ncol
        minw = [0.0] * ncol
        for _, c in rows:
            for ci, (_, toks) in enumerate(c):
                ws = [self.tok_width(t) for t in toks]
                kinds = self.kinds(toks)
                for line in layout.wrap_tokens(ws, kinds, float('inf')):
                    nat[ci] = max(nat[ci], sum(ws[i] for i in line))
                minw[ci] = max([minw[ci]] + [x for x, k in zip(ws, kinds) if k == 'w'])
        caps = layout.column_caps(nat, minw, layout.table_budget(w, ncol, self.m['cell_px']))
        laid = [[self.wrap(toks, caps[ci]) for ci, (_, toks) in enumerate(c)] for _, c in rows]
        self.meter.fill(k for r in laid for cell in r for line in cell for k in self.run_keys(line))
        lw = [[[self.line_width(line) for line in cell] for cell in r] for r in laid]
        colw = [max(max(cell) if cell else 0 for cell in (r[ci] for r in lw)) for ci in range(ncol)]

        out = []
        last = len(rows) - 1
        for ri, (header, c) in enumerate(rows):
            nlines = max(len(cell) for cell in laid[ri])
            spans = []
            for ci, (al, _toks) in enumerate(c):
                divs = []
                for line, width in zip(laid[ri][ci], lw[ri][ci]):
                    pl, pr = layout.align_pads(al, colw[ci], width)
                    style = ' style="padding-left:%dpx;padding-right:%dpx"' % (pl, pr) if pl or pr else ''
                    divs.append('<div class="t"%s>%s%s</div>' % (style, STRUT, self.emit(line)))
                divs += ['<div class="t">%s&nbsp;</div>' % STRUT] * (nlines - len(laid[ri][ci]))
                divs.append('<div class="sp"><img src="%s" width="%d" height="1"></div>'
                            % (SPACER_SRC, int(round(colw[ci])) + layout.SAFETY))
                cls = 'td'
                if header:
                    cls += ' th'
                if ci == ncol - 1:
                    cls += ' tdr'
                if ri == last:
                    cls += ' tdb'
                if not header and ri % 2 == 0:
                    cls += ' st'
                spans.append('<span class="%s">%s</span>' % (cls, ''.join(divs)))
            out.append('<div class="%s">%s</div>' % ('tr trl' if ri == last else 'tr', ''.join(spans)))
        out.append('<div class="tend"></div>')
        return ''.join(out)

    def front_matter(self, t, w, px):
        """Front matter as GitHub shows it: a table with the keys as the header row and the
        values as one row. Lists put one item per line; values outside the YAML subset show
        their source lines in the code font. Unreadable front matter stays a code block."""
        entries = frontmatter.parse(t.content)
        if entries is None:
            return self.code(t.content, t.map[0] + 1)
        base = t.map[0] + 1
        head = []
        vals = []
        for e in entries:
            st = _Style(True, False, False, False, None, None, base + e.key_row)
            toks = []
            self.word_tokens(toks, e.key, 'bold', px, st)
            head.append(('left', toks))
            toks = []
            if e.kind == 'scalar':
                lines = [(e.value, e.key_row)]
            else:
                lines = list(zip(e.value, e.item_rows))
            raw = e.kind == 'raw'
            font, size, cls = ('mono', self.m['code'], 'fmr') if raw else ('body', px, None)
            for k, (text, r) in enumerate(lines):
                st = _Style(False, False, False, False, None, cls, base + r)
                if k:
                    toks.append(_Tok('', 'n', font, size, st))
                if raw:
                    # Source indentation is kept: leading spaces become no-break spaces, which
                    # stay inside the first word.
                    stripped = text.lstrip(' ')
                    text = '\u00a0' * (len(text) - len(stripped)) + stripped
                self.word_tokens(toks, text, font, size, st)
            vals.append(('left', toks))
        return self.grid([(True, head), (False, vals)], w)

    def html_block(self, t, w):
        """(html, tight) of a raw HTML block. Without any subset tag it stays escaped source in a
        code box. Otherwise it is flowing text in which subset tags render and other tags stay
        escaped text; <details> is always open and its <summary> (or 'Details') is a marked title
        line. The content of a details element is the following blocks, rendered as usual;
        tight (no gap below) when the block ends with a title line."""
        pieces = html_pieces(t.content)
        if not any(p[0] == 'tag' and p[1] in HTML_SUBSET for p in pieces):
            self.tail_summary = False
            return self.code(t.content, t.map[0]), False
        row = t.map[0]
        items = []          # (html, is_title)
        buf = []
        stack = []
        summary = None      # inner html of an open <summary>
        pending = None      # row of a <details> that has no title line yet

        def close_spans(into):
            into.extend(_HTML_INLINE_SPANS[n][1] for n in reversed(stack))
            del stack[:]

        def flush():
            close_spans(buf)
            h = ''.join(buf)
            del buf[:]
            if h.strip():
                items.append(('<p>%s</p>' % h, False))

        def title(inner, r=None):
            if not inner:
                inner = self._run(DEFAULT_SUMMARY, row if r is None else r, 0)
            items.append(('<div class="sm">%s %s</div>' % (SUMMARY_MARKER, inner), True))

        for p in pieces:
            cur = summary if summary is not None else buf
            if p[0] == 'comment':
                row += p[1].count('\n')
                continue
            if p[0] == 'text':
                for k, seg in enumerate(p[1].split('\n')):
                    if k:
                        row += 1
                        cur.append(' ')
                    if pending is not None and summary is None and seg.strip():
                        title('', pending)
                        pending = None
                    cur.append(self._run(seg, row, 0))
                continue
            _, name, closing, attrs, raw = p
            if name == 'details' or (name == 'summary' and not closing and summary is None):
                if summary is not None:         # <details> inside an unclosed <summary>
                    close_spans(summary)
                    title(''.join(summary).strip())
                    summary = None
                flush()
                if pending is not None and name == 'details':
                    title('', pending)
                if name == 'details':
                    pending = None if closing else row
                else:
                    pending = None
                    summary = []
            elif name == 'summary':
                if closing and summary is not None:
                    close_spans(summary)
                    title(''.join(summary).strip())
                    summary = None
            elif name in HTML_SUBSET:
                if pending is not None and summary is None:
                    title('', pending)
                    pending = None
                cur.append(self.html_tag(p, row, 0, w, stack))
            else:
                cur.append(self._run(raw, row, 0))
            row += raw.count('\n')
        if summary is not None:
            close_spans(summary)
            title(''.join(summary).strip())
        flush()
        if pending is not None:
            title('', pending)
        self.tail_summary = bool(items) and items[-1][1]
        return self._join([(h, tight) for h, tight in items]), self.tail_summary

    def alert(self, t, inner, ul, w, px):
        kind = _ALERT_CLASS.get((t.meta or {}).get('kind', 'NOTE'), 'note')
        row = t.map[0] if t.map else None
        items = []
        for ct, cinner in _split_level(inner):
            if ct.type == 'alert_title_open':
                # The icon's gap is the title text's padding: minihtml ignores <img> padding.
                icon = theme.icon_html('alert-' + kind, self.ctx.theme, self.ctx.body_px)
                items.append(('<div class="alt">%s<span class="altx">%s</span></div>'
                              % (icon, self.inline(cinner[0].children, row)), False))
            else:
                items.append(self.node(ct, cinner, ul, w, px))
        return '<div class="bq al al-%s">%s</div>' % (kind, self._join(items))

    def list(self, t, inner, ul, w, px):
        ordered = t.type == 'ordered_list_open'
        items = [(it, body) for it, body in _split_level(inner) if it.type == 'list_item_open']
        task = any('checked' in (it.meta or {}) for it, _ in items)
        child_ul = ul + (0 if ordered else 1)
        indent = self.m['indent']
        depth = self.depth
        self.depth += 1
        try:
            return self._list(t, items, ordered, task, child_ul, ul, w, px, indent, depth)
        finally:
            self.depth -= 1

    def _list(self, t, items, ordered, task, child_ul, ul, w, px, indent, depth):
        if not ordered and not task:
            lis = []
            for k, (it, body) in enumerate(items):
                lis.append('<li%s>%s</li>' % (' class="n"' if k else '',
                                              self.nodes(_split_level(body), child_ul, w - indent, px)))
            return '<ul class="u%d">%s</ul>' % (min(ul, 2), ''.join(lis))
        start = t.attrGet('start')
        start = 1 if start is None else int(start)
        entries = []
        for k, (it, body) in enumerate(items):
            checked = (it.meta or {}).get('checked')
            if checked is not None:
                marker = ('icon', 'check-on' if checked else 'check-off')
            elif ordered:
                marker = ('text', list_marker(start + k, depth))
            else:
                marker = ('text', '\u2022')
            entries.append((marker, _split_level(body)))
        return self.hanging(entries, child_ul, w, px, indent)

    def hanging(self, entries, ul, w, px, indent):
        """Items whose marker hangs in the indent: marker box + pre-wrapped text box per item.

        entries: (marker, nodes) with marker ('text', s) or ('icon', name). minihtml has no
        outside markers, negative margins or text-indent, so the item's first paragraph is
        wrapped here by measurement and the marker box is padded to as many lines."""
        heads = []
        for marker, nodes in entries:
            toks = None
            if nodes and nodes[0][0].type == 'paragraph_open':
                t, pinner = nodes[0]
                inline_tok = pinner[0]
                row = inline_tok.map[0] if inline_tok.map else None
                toks = self.tokens(inline_tok.children, row, px,
                                   img_w=w - indent - layout.SAFETY)
                fn = _anchor_id(pinner)
                if fn is not None:
                    toks += self.backref_tokens(fn + 1, px)
            heads.append(toks)
        keys = [k for toks in heads if toks for k in self.measured_keys(toks)]
        keys += [('body', px, m[1]) for m, _ in entries if m[0] == 'text']
        keys.append(('body', px, ' '))
        self.meter.fill(keys)
        gap = self.meter.get(('body', px, ' '))
        icon = int(round(self.m['check']))
        text_w = w - indent - layout.SAFETY
        out = []
        for k, ((marker, nodes), toks) in enumerate(zip(entries, heads)):
            lines = self.wrap(toks, text_w) if toks is not None else [[]]
            text = '<br>'.join(self.emit(line) for line in lines) or '&nbsp;'
            rest = nodes[1:] if toks is not None else nodes
            more = ' n' if k else ''
            if toks is not None and rest and not nodes[0][0].hidden:
                more += ' g'
            if marker[0] == 'icon':
                # minihtml stretches an image whose line has a line-height, so the icon's line
                # keeps the natural height and only the filler lines take the text line height;
                # the zero-width space gives the icon line a baseline in one- and multi-line items.
                pl, pr = layout.marker_pads(indent, icon, gap)
                mark = ('<div class="ck">%s\u200b</div>%s'
                        % (theme.icon_html(marker[1], self.ctx.theme, icon),
                           '<div class="oi">&nbsp;</div>' * (len(lines) - 1)))
                out.append('<div class="hl%s"><span class="mk" style="padding-left:%dpx;'
                           'padding-right:%dpx">%s</span><span class="lc oi">%s</span></div>'
                           % (more, pl, pr, mark, text))
            else:
                pl, pr = layout.marker_pads(indent, self.meter.get(('body', px, marker[1])), gap)
                out.append('<div class="oi%s"><span class="mk" style="padding-left:%dpx;'
                           'padding-right:%dpx">%s%s</span><span class="lc">%s</span></div>'
                           % (more, pl, pr, _esc(marker[1]), '<br>&nbsp;' * (len(lines) - 1), text))
            body = self.nodes(rest, ul, w - indent, px) if rest else ''
            if body:
                out.append('<div class="oc">%s</div>' % body)
        return ''.join(out)

    def footnotes(self, inner, ul, w):
        px = self.m['fn'] * 1.0
        entries = []
        for t, body in _split_level(inner):
            if t.type != 'footnote_open':
                continue
            nodes = [(ct, cb) for ct, cb in _split_level(body) if ct.type != 'footnote_anchor']
            entries.append((('text', '%d.' % (t.meta['id'] + 1)), nodes))
        # The list's rule and top padding belong to the first note's block (one block per note).
        b = self.block
        first = b is None or b.index == 0 or self.doc.blocks[b.index - 1].kind != 'footnotes'
        return '<div class="%s">%s</div>' % ('fns fnt' if first else 'fns',
                                             self.hanging(entries, ul, w, px, self.m['fn_indent']))


def render_block(block: Block, doc: Document, ctx: RenderContext, measure, highlight=None,
                 image_size=None, remote=None) -> str:
    """measure(kind, px, texts) -> widths: kind is one of layout.FONT_KINDS (layout.measurer).
    highlight(info, code) -> html per code line (len == code lines) or None for plain text,
    where info is the fence info string; without it code blocks are plain.
    image_size(path) -> (w, h) or None of a local image (default: navigation.read_image_size,
    which reads the file header; image files are not part of any cache key).
    remote(url) -> local path of a downloaded http(s) image or None; without it (remote images
    off) remote images are alt text links. Its answers must be part of the caller's cache key."""
    r = _Renderer(doc, ctx, measure, highlight, image_size, block, remote)
    inner = r.nodes(_split_level(block.tokens), 0, ctx.avail, ctx.body_px)
    cls = 'blk k-%s' % block.kind
    if block.kind == 'html_block' and r.tail_summary:
        cls += ' dsum'      # a details title: its content follows without the block gap
    if (block.kind == 'footnotes' and block.index + 1 < len(doc.blocks)
            and doc.blocks[block.index + 1].kind == 'footnotes'):
        cls += ' fnx'
    if block.index == 0:
        cls += ' first'
    return _wrap(cls, inner, ctx)


def render_empty(ctx: RenderContext) -> str:
    return _wrap('blk k-empty first', '<p>Empty document</p>', ctx)
