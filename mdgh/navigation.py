# -*- coding: utf-8 -*-
import math
import os
import re
import struct
from bisect import bisect_right
from urllib.parse import unquote

# 한 글자 스킴은 드라이브 문자(C:\...)라서 스킴으로 보지 않는다.
_SCHEME = re.compile(r'^([A-Za-z][A-Za-z0-9+.\-]+):')
_EDIT = re.compile(r'^mdgh:e:(\d+)$')
_DRIVE = re.compile(r'^[A-Za-z]:')
_FOOTNOTE = re.compile(r'^#fn-(\d+)$')
_FOOTNOTE_BACK = re.compile(r'^#fnref-(\d+)$')


def block_for_line(starts, line):
    return max(0, bisect_right(starts, line) - 1)


def _height(ys, total_h, k):
    nxt = ys[k + 1] if k + 1 < len(ys) else total_h
    return nxt - ys[k]


def line_to_y(starts, ends, ys, total_h, line):
    if not starts:
        return 0.0
    line = min(max(line, starts[0]), ends[-1])
    k = block_for_line(starts, line)
    n = ends[k] - starts[k]
    h = _height(ys, total_h, k)
    if n <= 0 or h <= 0:
        return float(ys[k])
    frac = min(max((line - starts[k]) / n, 0.0), 1.0)
    return ys[k] + frac * h


def y_to_line(starts, ends, ys, total_h, y):
    if not starts:
        return 0
    y = min(max(y, ys[0]), total_h)
    k = max(0, bisect_right(ys, y) - 1)
    # 높이 0 블록은 건너뛰어 앞의 높이 있는 블록에 귀속시킨다.
    while k > 0 and _height(ys, total_h, k) <= 0:
        k -= 1
    n = ends[k] - starts[k]
    h = _height(ys, total_h, k)
    if n <= 0 or h <= 0:
        return starts[k]
    frac = min(max((y - ys[k]) / h, 0.0), 1.0)
    return starts[k] + min(int(math.floor(frac * n + 1e-9)), n - 1)


def screen_y_for_line(starts, ends, ys, total_h, line, viewport_y, viewport_h, line_h):
    """Screen height of the row's proportional preview y, kept where a whole editor line
    stays visible."""
    y = line_to_y(starts, ends, ys, total_h, line) - viewport_y
    return min(max(y, 0.0), max(0.0, viewport_h - line_h))


def restore_index(old_keys, old_index, new_keys):
    if not new_keys:
        return 0
    if 0 <= old_index < len(old_keys):
        key = old_keys[old_index]
        best = None
        for i, k in enumerate(new_keys):
            if k == key and (best is None or abs(i - old_index) < abs(best - old_index)):
                best = i
        if best is not None:
            return best
    return min(max(old_index, 0), len(new_keys) - 1)


def pending_block(pending, starts, keys, fragment_k=None):
    """Block a pending position ('slug' | 'index' | 'keys' | 'block' | 'line') points at in a
    document with these block starts and keys; fragment_k is the 'slug' fragment's block or None.
    Requires a non-empty doc. 'y' has no block."""
    kind = pending[0]
    if kind == 'slug':
        return 0 if fragment_k is None else fragment_k
    if kind == 'index':
        return min(pending[1], len(starts) - 1)
    if kind == 'keys':
        return restore_index(pending[1], pending[2], keys)
    return block_for_line(starts, pending[1])


def pending_line(pending, starts, ends, k):
    """Source line of a pending position whose block is k: the block start plus the in-block
    fraction ('keys' frac, 'line' the row itself, 'slug'/'index'/'block' the block start).
    'y' has no line."""
    kind = pending[0]
    if kind == 'y':
        return None
    if kind == 'line':
        return pending[1]
    if kind == 'keys':
        n = ends[k] - starts[k]
        if n <= 0:
            return starts[k]
        return starts[k] + min(int(math.floor(min(max(pending[3], 0.0), 1.0) * n + 1e-9)), n - 1)
    return starts[k]


def _known_height(ys, total_h, k):
    """Height of drawn block k, or None while it is not known (k not drawn, or k is the last
    drawn block and more follow). total_h: bottom of the last block when all are drawn, else None."""
    if k + 1 < len(ys):
        return ys[k + 1] - ys[k]
    if total_h is not None and k == len(ys) - 1:
        return total_h - ys[k]
    return None


def target_y(pending, starts, ends, ys, total_h, k):
    """y of a pending position in a block table, or None while its block's height is not known.

    starts/ends: all blocks; ys: y of the drawn blocks (a prefix); total_h: bottom of the last
    block when all are drawn, else None; k: the position's block (pending_block; unused for 'y'
    and an empty table)."""
    kind = pending[0]
    if kind == 'y':
        return pending[1]
    if not starts:
        return 0.0
    h = _known_height(ys, total_h, k) if k < len(ys) else None
    if h is None:
        return None
    if kind in ('slug', 'index', 'block'):
        return 0.0 if k == 0 else ys[k]
    if kind == 'keys':
        return ys[k] + pending[3] * h
    # 'line': the row's proportional y, kept at the same screen height.
    _, row, screen_y, at_top_ = pending
    if k == 0 and at_top_:
        return 0.0
    m = k + 1
    total = ys[m] if m < len(ys) else total_h
    return line_to_y(starts[:m], ends[:m], ys[:m], total, row) - screen_y


def can_show(y, all_drawn, drawn_h, viewport_h):
    """Whether the viewport can be put at y: with scroll_past_end off ST clamps a position whose
    screen is not filled by drawn content, so until everything is drawn it waits for one
    viewport below y (drawn_h: bottom of the drawn content)."""
    return all_drawn or drawn_h >= y + viewport_h


def staged_y(measured_y, ys, total_h, start):
    """y a block of a new tail would have once the old tail replaced from block start is gone,
    for a block drawn below that old tail (ys/total_h: the old, fully drawn table; measured_y:
    the drawn height measured when the block was added)."""
    return measured_y - (total_h - ys[start])


def drawing_top_line(starts, ends, ys, drawn_h, vy, pending_line=None):
    """Source line at the top of a preview whose blocks are only partly drawn.

    starts/ends: all blocks; ys: y of the drawn blocks (a prefix); drawn_h: bottom of the drawn
    content; vy: y to look up. A pending position not yet applied is where the user was, while
    the viewport shows whatever ST clamped it to, so it wins over the drawn table."""
    if pending_line is not None:
        return pending_line
    m = len(ys)
    if m == 0 or vy < ys[0]:
        return 0
    return y_to_line(starts[:m], ends[:m], ys, drawn_h, vy)


def at_top(ys, vy, pending_line=None):
    """Whether leaving the preview puts the source at its first row: nothing is drawn, or the
    viewport is above the first block. A pending line is a position to restore, not the top,
    even though ST clamps the viewport of a partly drawn preview near y 0."""
    if pending_line is not None:
        return False
    return not ys or vy < ys[0]


def classify_link(href):
    m = _EDIT.match(href)
    if m:
        return ('edit', int(m.group(1)))
    m = _FOOTNOTE.match(href)
    if m:
        return ('footnote', int(m.group(1)))
    m = _FOOTNOTE_BACK.match(href)
    if m:
        return ('footnote_back', int(m.group(1)))
    if href.startswith('#'):
        return ('anchor', unquote(href[1:]))
    m = _SCHEME.match(href)
    if m:
        if m.group(1).lower() in ('http', 'https', 'mailto'):
            return ('web', href)
        return ('other', href)
    if not href or href.startswith('//'):
        return ('other', href)
    path, sep, slug = href.partition('#')
    path = unquote(path)
    # Only document-relative paths: an absolute, drive or UNC path in a document would make
    # the click touch arbitrary locations (a UNC path triggers SMB authentication).
    if not path or path[0] in '/\\' or _DRIVE.match(path):
        return ('other', href)
    return ('file', path, unquote(slug) if slug else None)


def resolve_file_link(doc_dir, path):
    return os.path.normpath(os.path.join(doc_dir, path))


def fragment_block(fragment, slugs, notes, refs):
    """Block index a same-document fragment points at, or None.

    fragment: decoded text after '#'. 'fn-<n>' / 'fnref-<n>' are the renderer's footnote targets
    (notes / refs: 1-based number -> block, blocks.footnote_blocks); anything else is a heading
    slug (slugs: per block, None for non-headings), compared exactly first, then ignoring case."""
    m = _FOOTNOTE.match('#' + fragment)
    if m and int(m.group(1)) in notes:
        return notes[int(m.group(1))]
    m = _FOOTNOTE_BACK.match('#' + fragment)
    if m and int(m.group(1)) in refs:
        return refs[int(m.group(1))]
    for i, s in enumerate(slugs):
        if s is not None and s == fragment:
            return i
    low = fragment.lower()
    for i, s in enumerate(slugs):
        if s is not None and s.lower() == low:
            return i
    return None


# ---------------------------------------------------------------- images

IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif')


def image_source(doc_dir, src):
    """Where an image's src points: ('local', absolute path) for a document-relative PNG/JPG/GIF,
    ('remote', url) for http(s), ('alt', None) for everything else (no document folder, absolute,
    drive or UNC paths, other schemes, other formats such as SVG)."""
    src = (src or '').strip()
    m = _SCHEME.match(src)
    if m:
        if m.group(1).lower() in ('http', 'https'):
            return ('remote', src)
        return ('alt', None)
    if not src or src.startswith('//') or not doc_dir:
        return ('alt', None)
    path = unquote(re.split(r'[?#]', src, maxsplit=1)[0])
    if not path or path[0] in '/\\' or _DRIVE.match(path):
        return ('alt', None)
    if os.path.splitext(path)[1].lower() not in IMAGE_EXTS:
        return ('alt', None)
    return ('local', os.path.normpath(os.path.join(doc_dir, path)))


def file_src(path):
    """minihtml src of a local file: file:// + the absolute path with forward slashes and no
    percent-encoding (the only form minihtml shows)."""
    return 'file://' + path.replace('\\', '/')


def image_size(f):
    """(width, height) in px from a PNG, GIF or JPEG header read from binary stream f, or None."""
    head = f.read(26)
    if head[:8] == b'\x89PNG\r\n\x1a\n' and head[12:16] == b'IHDR':
        w, h = struct.unpack('>II', head[16:24])
        return (w, h) if w and h else None
    if head[:6] in (b'GIF87a', b'GIF89a'):
        w, h = struct.unpack('<HH', head[6:10])
        return (w, h) if w and h else None
    if head[:2] != b'\xff\xd8':
        return None
    f.seek(2)
    while True:
        b = f.read(1)
        while b and b != b'\xff':
            b = f.read(1)
        while b == b'\xff':
            b = f.read(1)
        if not b:
            return None
        marker = b[0]
        if marker in (0x01,) or 0xd0 <= marker <= 0xd9:
            continue   # markers without a length
        seg = f.read(2)
        if len(seg) < 2:
            return None
        n = struct.unpack('>H', seg)[0]
        # Start of frame: every SOFn except DHT (c4), JPG (c8) and DAC (cc).
        if 0xc0 <= marker <= 0xcf and marker not in (0xc4, 0xc8, 0xcc):
            data = f.read(5)
            if len(data) < 5:
                return None
            h, w = struct.unpack('>HH', data[1:5])
            return (w, h) if w and h else None
        f.seek(n - 2, 1)


def read_image_size(path):
    """image_size of a file, or None when it cannot be read."""
    # A document can name a device (CON, NUL, a pipe) as an image; opening it would block the
    # main thread, so only regular files are read.
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'rb') as f:
            return image_size(f)
    except OSError:
        return None


_LENGTH = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*(px|%)?\s*$')
# Upper bound of an image's display width and height. Header sizes and width/height attributes
# come from the document, and one huge image would make a phantom too large to lay out.
MAX_IMAGE_PX = 8192


def html_length(value, max_w):
    """px of an HTML width/height attribute ('120', '120px', '50%' of max_w), or None."""
    m = _LENGTH.match(value or '')
    if not m:
        return None
    v = float(m.group(1))
    if m.group(2) == '%':
        v = v * max(0, int(max_w)) / 100.0
    if not math.isfinite(v):    # a long digit run parses to inf
        return None
    v = int(round(min(v, MAX_IMAGE_PX)))
    return v if v > 0 else None


def attr_image_size(w, h, width, height, max_w):
    """Display size of an <img> with natural size (w, h) and width/height attributes (raw
    strings or None): both given are used as they are, one given keeps the aspect ratio; the
    result is then fitted to max_w like a Markdown image."""
    aw = html_length(width, max_w)
    ah = html_length(height, max_w)
    if aw and ah:
        w, h = aw, ah
    elif aw:
        w, h = aw, max(1, int(round(h * aw / float(w))))
    elif ah:
        w, h = max(1, int(round(w * ah / float(h)))), ah
    return fit_image(w, h, max_w)


def fit_image(w, h, max_w):
    """Display size: the natural size, scaled down (aspect kept) to at most max_w wide and to
    at most MAX_IMAGE_PX on either side."""
    max_w = int(max_w)
    limit = min(max_w, MAX_IMAGE_PX) if max_w > 0 else MAX_IMAGE_PX
    w, h = int(w), int(h)
    if w > limit:
        w, h = limit, max(1, int(round(h * limit / float(w))))
    if h > MAX_IMAGE_PX:
        w, h = max(1, int(round(w * MAX_IMAGE_PX / float(h)))), MAX_IMAGE_PX
    return w, h
