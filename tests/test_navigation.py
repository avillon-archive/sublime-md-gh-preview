# -*- coding: utf-8 -*-
import io
import os
import struct

from mdgh.navigation import (MAX_IMAGE_PX, at_top, attr_image_size, block_for_line, classify_link,
                             file_src, fit_image, fragment_block,
                             drawing_top_line, image_size, image_source, line_to_y, pending_block, pending_line,
                             can_show, read_image_size, resolve_file_link, restore_index,
                             screen_y_for_line, staged_y, target_y, y_to_line)

STARTS = [0, 4, 10, 10, 15]
ENDS = [4, 10, 10, 15, 20]
YS = [0, 100, 300, 300, 400]
TOTAL = 600


def test_block_for_line():
    assert block_for_line([0, 4, 10], 0) == 0
    assert block_for_line([0, 4, 10], 4) == 1
    assert block_for_line([0, 4, 10], 99) == 2


def test_line_to_y_proportional():
    assert line_to_y(STARTS, ENDS, YS, TOTAL, 0) == 0
    assert line_to_y(STARTS, ENDS, YS, TOTAL, 2) == 50
    assert line_to_y(STARTS, ENDS, YS, TOTAL, 7) == 200
    assert line_to_y(STARTS, ENDS, YS, TOTAL, 17) == 480


def test_line_to_y_clamps_and_degenerate():
    assert line_to_y(STARTS, ENDS, YS, TOTAL, -5) == 0
    assert line_to_y(STARTS, ENDS, YS, TOTAL, 999) == 600
    assert line_to_y([], [], [], 0, 3) == 0
    # 길이 0 블록(10..10)은 블록 top 으로 간다
    assert line_to_y([0, 5], [5, 5], [0, 100], 100, 5) == 100
    # 높이 0 블록
    assert line_to_y([0, 5], [5, 10], [0, 0], 0, 3) == 0


def test_y_to_line_clamps_and_empty():
    assert y_to_line(STARTS, ENDS, YS, TOTAL, -10) == 0
    assert y_to_line(STARTS, ENDS, YS, TOTAL, 10_000) == 19
    assert y_to_line([], [], [], 0, 5) == 0


def test_round_trip_lines():
    for line in range(20):
        y = line_to_y(STARTS, ENDS, YS, TOTAL, line)
        assert y_to_line(STARTS, ENDS, YS, TOTAL, y) == line


def test_round_trip_y_within_one_line_height():
    for y in range(0, 600, 7):
        back = line_to_y(STARTS, ENDS, YS, TOTAL, y_to_line(STARTS, ENDS, YS, TOTAL, y))
        assert 0 <= y - back <= 40 + 1e-6  # 가장 큰 줄 높이(200/5) 이내


def test_restore_finds_same_block_after_insertion():
    old = ['a', 'b', 'c', 'd']
    assert restore_index(old, 2, ['x', 'y'] + old) == 4
    assert restore_index(old, 2, ['a', 'b', 'd']) == 2  # c 사라짐 -> 같은 번호 (d 위치)


def test_restore_prefers_nearest_duplicate():
    old = ['a', 'dup', 'b', 'c', 'd', 'e', 'dup']
    new = ['dup', 'a', 'b', 'dup', 'c', 'd', 'e', 'f', 'dup']
    assert restore_index(old, 6, new) == 8
    assert restore_index(old, 1, new) == 0


def test_restore_clamps_when_missing():
    assert restore_index(['a', 'b', 'c'], 2, ['x']) == 0
    assert restore_index(['a', 'b', 'c'], 0, []) == 0
    assert restore_index(['a'], 5, ['p', 'q', 'r']) == 2


def test_pending_block_per_kind():
    keys = ['a', 'b', 'c', 'd', 'e']
    assert pending_block(('keys', ['x', 'c'], 1, 0.5), STARTS, keys) == 2
    assert pending_block(('block', 12), STARTS, keys) == block_for_line(STARTS, 12)
    assert pending_block(('line', 17, 30.0, False), STARTS, keys) == 4
    assert pending_block(('index', 99), STARTS, keys) == 4
    assert pending_block(('slug', 's'), STARTS, keys, 3) == 3
    assert pending_block(('slug', 'missing'), STARTS, keys, None) == 0


def test_pending_line_per_kind():
    assert pending_line(('keys', [], 0, 0.5), STARTS, ENDS, 1) == 7
    assert pending_line(('keys', [], 0, 1.0), STARTS, ENDS, 1) == 9
    assert pending_line(('keys', [], 0, 0.5), STARTS, ENDS, 2) == 10  # empty block
    assert pending_line(('line', 13, 0.0, False), STARTS, ENDS, 3) == 13
    assert pending_line(('block', 12), STARTS, ENDS, 3) == 10
    assert pending_line(('slug', 's'), STARTS, ENDS, 4) == 15
    assert pending_line(('y', 5.0), STARTS, ENDS, 0) is None


def test_drawing_top_line_uses_drawn_table_or_pending():
    ys = YS[:3]  # blocks 0..2 drawn
    assert drawing_top_line(STARTS, ENDS, ys, 300, 50) == 2
    assert drawing_top_line(STARTS, ENDS, ys, 300, 150) == 5
    assert drawing_top_line(STARTS, ENDS, ys, 300, -5) == 0
    assert drawing_top_line(STARTS, ENDS, [], 0, 50) == 0
    # a pending position outranks the clamped viewport
    assert drawing_top_line(STARTS, ENDS, ys, 300, 50, 17) == 17


def test_classify_links():
    assert classify_link('mdgh:e:12') == ('edit', 12)
    assert classify_link('mdgh:e:x') == ('other', 'mdgh:e:x')
    assert classify_link('https://a.b/c#d') == ('web', 'https://a.b/c#d')
    assert classify_link('HTTP://a.b') == ('web', 'HTTP://a.b')
    assert classify_link('mailto:a@b.c')[0] == 'web'
    assert classify_link('#my-%ED%95%9C') == ('anchor', 'my-한')
    assert classify_link('docs/a%20b.md') == ('file', 'docs/a b.md', None)
    assert classify_link('../x.md#sec%201') == ('file', '../x.md', 'sec 1')
    assert classify_link('x.md#') == ('file', 'x.md', None)
    assert classify_link('ftp://h/f')[0] == 'other'
    assert classify_link('javascript:alert(1)')[0] == 'other'
    assert classify_link('')[0] == 'other'
    for p in (r'\\host\share\x.md', '%5C%5Chost%5Cshare%5Cx.md', 'C:/x.md', r'C:\x.md',
              '/abs/x.md', r'\x.md'):
        assert classify_link(p)[0] == 'other', p


def test_resolve_file_link(tmp_path):
    d = str(tmp_path / 'doc')
    assert resolve_file_link(d, '../x/a.md') == os.path.normpath(str(tmp_path / 'x' / 'a.md'))
    assert resolve_file_link(d, 'b.md') == os.path.join(d, 'b.md')


# ---------------------------------------------------------------- footnotes, fragments, images

def test_classify_footnote_links():
    assert classify_link('#fn-3') == ('footnote', 3)
    assert classify_link('#fnref-12') == ('footnote_back', 12)
    assert classify_link('#fn-x') == ('anchor', 'fn-x')


def test_fragment_block_maps_footnotes_and_slugs():
    slugs = ['intro', None, 'Mixed-Case', None, None]
    notes, refs = {1: 3, 2: 4}, {1: 1, 2: 1}
    assert fragment_block('fn-2', slugs, notes, refs) == 4
    assert fragment_block('fnref-1', slugs, notes, refs) == 1
    assert fragment_block('fn-9', slugs, notes, refs) is None
    assert fragment_block('intro', slugs, notes, refs) == 0
    assert fragment_block('mixed-case', slugs, notes, refs) == 2
    assert fragment_block('nope', slugs, notes, refs) is None


def png(w, h):
    return (b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', w, h)
            + b'\x08\x02\x00\x00\x00' + b'\x00' * 4)


def gif(w, h):
    return b'GIF89a' + struct.pack('<HH', w, h) + b'\x00\x00\x00'


def jpeg(w, h, sof=0xc0):
    app0 = b'\xff\xe0' + struct.pack('>H', 16) + b'JFIF\x00' + b'\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    dqt = b'\xff\xdb' + struct.pack('>H', 4) + b'\x00\x00'
    dht = b'\xff\xc4' + struct.pack('>H', 5) + b'\x00\x00\x00'   # c4 is not a frame header
    frame = bytes([0xff, sof]) + struct.pack('>HBHHB', 11, 8, h, w, 3) + b'\x01\x11\x00'
    return b'\xff\xd8' + app0 + dqt + dht + frame + b'\xff\xd9'


def test_image_size_reads_png_gif_and_jpeg_headers():
    assert image_size(io.BytesIO(png(640, 3))) == (640, 3)
    assert image_size(io.BytesIO(gif(17, 300))) == (17, 300)
    assert image_size(io.BytesIO(jpeg(1024, 77))) == (1024, 77)
    assert image_size(io.BytesIO(jpeg(5, 9, sof=0xc2))) == (5, 9)      # progressive


def test_image_size_rejects_other_and_truncated_data():
    for data in (b'', b'<svg xmlns="http://www.w3.org/2000/svg"/>', png(0, 5), b'\xff\xd8\xff\xe0',
                 jpeg(10, 10)[:-20]):
        assert image_size(io.BytesIO(data)) is None, data


def test_read_image_size_with_korean_and_space_path(tmp_path):
    d = tmp_path / '한글 폴더'
    d.mkdir()
    (d / '그림 1.png').write_bytes(png(300, 200))
    assert read_image_size(str(d / '그림 1.png')) == (300, 200)
    assert read_image_size(str(d / 'missing.png')) is None


def test_image_source_resolves_only_document_relative_bitmaps(tmp_path):
    doc_dir = str(tmp_path / '문서 폴더')
    assert image_source(doc_dir, 'img/%EA%B7%B8%EB%A6%BC%201.png') == (
        'local', os.path.join(doc_dir, 'img', '그림 1.png'))
    assert image_source(doc_dir, '../a.JPG?raw=1')[0] == 'local'
    assert image_source(doc_dir, 'b.jpeg')[0] == 'local'
    assert image_source(doc_dir, 'c.gif#x')[0] == 'local'
    assert image_source(doc_dir, 'https://x.test/a.png') == ('remote', 'https://x.test/a.png')
    for src in ('d.svg', 'e.webp', 'noext', '', 'C:/x.png', r'C:\x.png', '/x.png', r'\\host\s\x.png',
                '%5C%5Chost%5Cs%5Cx.png', '//host/x.png', 'data:image/png;base64,AAAA',
                'file:///C:/x.png', 'ftp://h/x.png'):
        assert image_source(doc_dir, src) == ('alt', None), src
    assert image_source('', 'a.png') == ('alt', None)       # unsaved buffer


def test_file_src_is_slash_path_without_percent_encoding():
    src = file_src(r'C:\문서 폴더\그림 1.png')
    assert src == 'file://C:/문서 폴더/그림 1.png'


def test_fit_image_scales_down_keeping_aspect_never_up():
    assert fit_image(300, 200, 600) == (300, 200)
    assert fit_image(1200, 300, 600) == (600, 150)
    assert fit_image(1000, 1, 500) == (500, 1)
    assert fit_image(800, 600, 0) == (800, 600)


def test_image_size_from_document_values_is_bounded():
    # A header or an attribute can claim any size; the display size stays layoutable.
    w, h = fit_image(10, 2 ** 31 - 1, 600)
    assert h <= MAX_IMAGE_PX and w >= 1
    w, h = fit_image(2 ** 31 - 1, 2 ** 31 - 1, 0)
    assert w <= MAX_IMAGE_PX and h <= MAX_IMAGE_PX
    assert attr_image_size(100, 50, '9' * 400, None, 600)[0] <= 600     # parses to inf
    w, h = attr_image_size(100, 50, '10', '9' * 12, 600)
    assert h <= MAX_IMAGE_PX


# Blocks: rows [0,2) y 0..50, rows [2,6) y 50..130, rows [6,7) y 130..150.
SCREEN_STARTS, SCREEN_ENDS, SCREEN_YS, SCREEN_TOTAL = [0, 2, 6], [2, 6, 7], [0.0, 50.0, 130.0], 150.0


def test_row_keeps_its_proportional_screen_height():
    # Row 4 is half way through block 1: y 90; the viewport top is at 30.
    assert screen_y_for_line(SCREEN_STARTS, SCREEN_ENDS, SCREEN_YS, SCREEN_TOTAL, 4, 30.0, 400.0, 20.0) == 60.0


def test_row_above_the_viewport_goes_to_the_top():
    assert screen_y_for_line(SCREEN_STARTS, SCREEN_ENDS, SCREEN_YS, SCREEN_TOTAL, 2, 80.0, 400.0, 20.0) == 0.0


def test_row_near_the_bottom_stays_fully_visible():
    # Row 6 is at y 130, 110 below the top of a 100px viewport with 20px lines.
    assert screen_y_for_line(SCREEN_STARTS, SCREEN_ENDS, SCREEN_YS, SCREEN_TOTAL, 6, 20.0, 100.0, 20.0) == 80.0


def test_at_top_yields_to_a_pending_line():
    ys = [26.0, 188.0]
    assert at_top(ys, 0.0) is True
    assert at_top(ys, 100.0) is False
    assert at_top([], 500.0) is True
    # ST clamps a partly drawn preview near y 0; the restore position still wins.
    assert at_top(ys, 0.0, 5739) is False


# ---------------------------------------------------------------- pending positions, staged tail

VH = 100.0   # viewport height in the position tests


def show_y(p, ys, total, k, drawn_h):
    """The y a pending position is applied at, or None while it waits (the controller's use)."""
    y = target_y(p, STARTS, ENDS, ys, total, k)
    return y if y is not None and can_show(y, total is not None, drawn_h, VH) else None


def test_position_waits_for_its_block_and_a_screen_below_it():
    # keys position half way through block 1 (y 100..300): y 200.
    p = ('keys', [], 1, 0.5)
    ys = YS[:3]   # blocks 0..2 drawn, more follow
    assert show_y(p, ys, None, 1, 299.0) is None
    assert show_y(p, ys, None, 1, 300.0) == 200
    # Block 1 is the last drawn one: its height is not known yet.
    assert target_y(p, STARTS, ENDS, YS[:2], None, 1) is None


def test_position_shows_at_once_when_everything_is_drawn():
    # The content below the position is shorter than the viewport, but nothing more comes.
    assert show_y(('keys', [], 4, 0.5), YS, TOTAL, 4, TOTAL) == 500


def test_block_positions_keep_the_toolbar_visible_for_block_0():
    for kind in ('slug', 'index', 'block'):
        assert target_y((kind, 0), STARTS, ENDS, YS, TOTAL, 0) == 0.0
        assert target_y((kind, 0), STARTS, ENDS, YS, TOTAL, 1) == 100
    assert target_y(('index', 4), STARTS, ENDS, YS[:4], None, 3) is None


def test_line_position_keeps_the_row_at_its_screen_height():
    # Row 7 is half way through block 1 (y 200); it was 30 px below the top of the screen.
    assert target_y(('line', 7, 30.0, False), STARTS, ENDS, YS, TOTAL, 1) == 170
    assert target_y(('line', 2, 30.0, True), STARTS, ENDS, YS, TOTAL, 0) == 0.0


def test_y_position_and_empty_document():
    assert show_y(('y', 250.0), YS[:3], None, None, 340.0) is None
    assert show_y(('y', 250.0), YS[:3], None, None, 350.0) == 250.0
    assert target_y(('keys', [], 0, 0.0), [], [], [], 0.0, None) == 0.0


def test_staged_tail_resolves_like_a_table_drawn_from_scratch():
    # Old document: heights 100, 200, 0, 100, 200 (YS, TOTAL). The edit grows block 1 to 250, so
    # blocks 1.. are drawn again. The old tail (blocks 1..4, 500 px) stays on screen and the new
    # blocks are added below it: each is measured 500 px lower than it will be.
    new_h = [100, 250, 0, 100, 200]
    scratch = [sum(new_h[:k]) for k in range(len(new_h))]
    start = 1
    measured = [TOTAL + sum(new_h[start:k]) for k in range(start, len(new_h))]
    staged = YS[:start] + [staged_y(m, YS, TOTAL, start) for m in measured]
    assert staged == scratch
    new_total = staged_y(TOTAL + sum(new_h[start:]), YS, TOTAL, start)
    assert new_total == sum(new_h)
    # The position kept by the update (a quarter into block 3, y 375) lands where it would in
    # the new table, once the staged content reaches one screen below it.
    p = ('keys', [], 3, 0.25)
    assert show_y(p, staged[:4], None, 3, 450.0) is None
    assert show_y(p, staged, None, 3, 470.0) is None
    assert show_y(p, staged, None, 3, 475.0) == 375
    assert show_y(p, staged, new_total, 3, new_total) == 375
