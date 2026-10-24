# -*- coding: utf-8 -*-
import pytest

from mdgh import frontmatter


def table(text):
    return [(e.key, e.kind, e.value, e.key_row, e.item_rows) for e in frontmatter.parse(text)]


def test_scalars_quoted_strings_and_lists_are_read():
    text = ('title: Hello world\n'
            'quoted: "a \\"b\\" # not a comment"\n'
            "single: 'it''s'\n"
            'commented: plain # trailing comment\n'
            'url: https://x.test/a#frag\n'
            'empty:\n'
            'inline: [a, "b, c", \'d\']\n'
            'block:\n'
            '  - one\n'
            '  - "two"\n'
            'flush:\n'
            '- p\n'
            '- q\n')
    assert table(text) == [
        ('title', 'scalar', 'Hello world', 0, [0]),
        ('quoted', 'scalar', 'a "b" # not a comment', 1, [1]),
        ('single', 'scalar', "it's", 2, [2]),
        ('commented', 'scalar', 'plain', 3, [3]),
        ('url', 'scalar', 'https://x.test/a#frag', 4, [4]),
        ('empty', 'scalar', '', 5, [5]),
        ('inline', 'list', ['a', 'b, c', 'd'], 6, [6, 6, 6]),
        ('block', 'list', ['one', 'two'], 7, [8, 9]),
        ('flush', 'list', ['p', 'q'], 10, [11, 12]),
    ]


def test_blank_and_comment_lines_between_keys_are_skipped():
    assert table('# c\na: 1\n\n# c2\nb: 2\n') == [('a', 'scalar', '1', 1, [1]),
                                                ('b', 'scalar', '2', 4, [4])]


@pytest.mark.parametrize('value_lines,rows,value', [
    (['nested:', '  a: 1', '  b:', '    - x'], [1, 2, 3], ['  a: 1', '  b:', '    - x']),   # nested mapping
    (['nested: |', '  line one', '  line two'], [0, 1, 2], ['|', '  line one', '  line two']),  # block scalar
    (['nested: [a, [b]]'], [0], ['[a, [b]]']),                 # nested flow list
    (['nested: {a: 1}'], [0], ['{a: 1}']),                     # flow mapping
    (['nested: first', '  continued'], [0, 1], ['first', '  continued']),    # multi-line plain scalar
    (['nested:', '  - a: 1'], [1], ['  - a: 1']),              # list of mappings
])
def test_values_outside_the_subset_keep_their_source_lines(value_lines, rows, value):
    entries = frontmatter.parse('\n'.join(value_lines + ['after: ok']))
    raw, after = entries
    assert raw.key == 'nested' and raw.kind == 'raw' and raw.key_row == 0
    assert raw.item_rows == rows
    assert raw.value == value
    assert (after.key, after.kind, after.value) == ('after', 'scalar', 'ok')


@pytest.mark.parametrize('text', [
    '',                      # nothing to show
    '\n\n',
    '- a\n- b',              # top level is a sequence
    '  a: 1',                # indented before any key
    'just text',             # not a key
    'a: 1\nplain line',      # a later top-level line that is not a key
    '"unterminated: 1',
])
def test_front_matter_that_is_not_a_readable_mapping_is_none(text):
    assert frontmatter.parse(text) is None
