# -*- coding: utf-8 -*-
import pytest

from mdgh import blocks

FRONT = '---\ntitle: x\n---\n\n# Head\n\ntext\n'
DOCS = {
    'empty': '',
    'one char': 'x',
    'only newline': '\n',
    'leading blank lines': '\n\n# t\n\ntext',
    'trailing blank lines': 'a\n\n\n',
    'front matter': FRONT,
    'comment between': 'a\n\n<!-- c -->\n\nb\n',
    'comment first': '<!-- c -->\n\nb',
    'comment only': '<!-- c -->\n',
    'multiline comment': 'a\n\n<!--\nx\ny\n-->\nb\n',
    'footnote': 'a[^1]\n\n[^1]: note\n\nlast\n',
    'footnote only': '[^1]: note\n',
    'mixed': '# h\n\n- a\n- b\n\n> q\n\n```py\nx\n```\n\n| a |\n|---|\n| 1 |\n\n---\n\ntail',
    'crlf': 'a\r\n\r\nb\r\n',
}


def lines_of(text):
    return text.replace('\r\n', '\n').split('\n') if text else []


@pytest.mark.parametrize('name', sorted(DOCS))
def test_ranges_tile_all_lines(name):
    text = DOCS[name]
    doc = blocks.parse(text)
    assert doc.line_count == len(lines_of(text))
    if name == 'empty':
        assert doc.blocks == []
    if not doc.blocks:
        return
    assert doc.blocks[0].start == 0
    for a, b in zip(doc.blocks, doc.blocks[1:]):
        assert a.end == b.start
    assert doc.blocks[-1].end == doc.line_count
    for i, b in enumerate(doc.blocks):
        assert b.index == i
        assert b.start <= b.map_start <= b.map_end <= b.end
        if b.kind != 'footnotes':
            assert b.src == '\n'.join(lines_of(text)[b.map_start:b.map_end])


@pytest.mark.parametrize('text,count', [('a', 1), ('a\n', 2), ('a\r\nb', 2), ('\n', 2)])
def test_line_count_matches_editor_rows(text, count):
    assert blocks.parse(text).line_count == count


def test_comment_only_html_block_is_dropped_but_other_html_stays():
    doc = blocks.parse('a\n\n<!-- c -->\n\n<div>x</div>\n\nb')
    assert [b.kind for b in doc.blocks] == ['paragraph', 'html_block', 'paragraph']
    assert 'div' in doc.blocks[1].src


def test_dropped_comment_lines_join_previous_block():
    doc = blocks.parse('a\n\n<!-- c -->\n\nb\n')
    assert (doc.blocks[0].start, doc.blocks[0].end) == (0, 4)
    assert (doc.blocks[1].start, doc.blocks[1].end) == (4, 6)


def test_front_matter_is_first_block():
    doc = blocks.parse(FRONT)
    assert [b.kind for b in doc.blocks] == ['front_matter', 'heading', 'paragraph']
    assert doc.blocks[0].start == 0


def test_footnote_list_is_a_last_empty_range_block():
    doc = blocks.parse('a[^1]\n\n[^1]: note\n')
    last = doc.blocks[-1]
    assert last.kind == 'footnotes'
    assert last.start == last.end == doc.line_count


def test_key_ignores_position_but_html_key_does_not():
    a = blocks.parse('para\n\ntail').blocks[0]
    b = blocks.parse('\n\npara\n\ntail').blocks[0]
    assert a.key == b.key
    assert a.html_key != b.html_key
    assert blocks.parse('other\n\ntail').blocks[0].key != a.key


def test_key_changes_with_footnote_number():
    alone = blocks.parse('x[^a]\n\n[^a]: A\n').blocks[0]
    second = blocks.parse('y[^b]\n\nx[^a]\n\n[^a]: A\n[^b]: B\n').blocks[1]
    assert alone.src == second.src
    assert alone.key != second.key


@pytest.mark.parametrize('text,expected', [
    ('Hello World', 'hello-world'),
    ("What's up? (v2.0)", 'whats-up-v20'),
    ('한글 제목', '한글-제목'),
    ('snake_case and-dash', 'snake_case-and-dash'),
    ('A - B', 'a---b'),
    ('Ünïcode Ñame', 'ünïcode-ñame'),
    ('', ''),
])
def test_slugify_follows_github_rules(text, expected):
    assert blocks.slugify(text, {}) == expected


def test_slugify_repeats_get_numeric_suffix():
    seen = {}
    assert [blocks.slugify('Dup', seen) for _ in range(3)] == ['dup', 'dup-1', 'dup-2']


def test_slugify_skips_suffix_already_taken():
    seen = {}
    assert [blocks.slugify(t, seen) for t in ('x-1', 'x', 'x')] == ['x-1', 'x', 'x-2']


def test_heading_slug_uses_rendered_text_and_counts_duplicates():
    doc = blocks.parse('# Foo *bar* `code`\n\n## Foo bar code\n\ntext\n\nSetext\n===\n')
    slugs = [b.slug for b in doc.blocks if b.kind == 'heading']
    assert slugs == ['foo-bar-code', 'foo-bar-code-1', 'setext']
    assert all(b.slug is None for b in doc.blocks if b.kind != 'heading')


def test_headings_list_level_and_plain_text():
    doc = blocks.parse('# One *a*\n\ntext\n\n### Three `c`\n\nSetext\n---\n')
    assert blocks.headings(doc) == [(0, 1, 'One a'), (2, 3, 'Three c'), (3, 2, 'Setext')]


def test_each_footnote_is_its_own_block_with_note_and_first_reference():
    doc = blocks.parse('intro\n\nx[^b] y[^a]\n\nz[^a]\n\n[^a]: A\n[^b]: B\n')
    kinds = [b.kind for b in doc.blocks]
    assert kinds == ['paragraph', 'paragraph', 'paragraph', 'footnotes', 'footnotes']
    notes, refs = blocks.footnote_blocks(doc)
    # notes are numbered in order of first reference
    assert notes == {1: 3, 2: 4}
    assert refs == {1: 1, 2: 1}


def test_footnote_block_key_changes_when_it_stops_being_last():
    one = blocks.parse('x[^a]\n\n[^a]: A\n').blocks[-1]
    two = blocks.parse('x[^a] y[^b]\n\n[^a]: A\n[^b]: B\n').blocks
    assert two[-2].kind == two[-1].kind == 'footnotes'
    assert one.key != two[-2].key
