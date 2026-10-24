# -*- coding: utf-8 -*-
import pytest

from mdgh import highlight

FG = '#1f2328'


@pytest.mark.parametrize('info,expected', [
    ('Python {linenos}', 'x.py'), ('{python}', 'x.py'), ('SH', 'x.sh'),
    ('dockerfile', 'Dockerfile'), ('rs', 'x.rs'),
])
def test_info_string_resolves_to_a_syntax_file_name(info, expected):
    assert highlight.file_name_for(info) == expected


@pytest.mark.parametrize('info', [None, '   ', 'text'])
def test_no_language_or_explicit_plain_means_no_highlighting(info):
    assert highlight.file_name_for(info) is None


def test_gaps_between_tokens_are_kept_and_default_color_is_not_wrapped():
    text = 'if x:'
    toks = [(0, 2, '#cf222e', False, False), (3, 4, FG, False, False)]
    (line,) = highlight.assemble(text, toks, FG)
    assert line == '<span style="color:#cf222e">if</span> x:'


def test_bold_and_italic_use_tags_inside_the_color_span():
    (line,) = highlight.assemble('ab', [(0, 1, '#0550ae', True, False), (1, 2, '#0550ae', False, True)], FG)
    assert line == ('<span style="color:#0550ae"><b>a</b></span>'
                    '<span style="color:#0550ae"><i>b</i></span>')


def test_equal_neighbours_merge_and_text_is_escaped():
    toks = [(0, 1, '#0a3069', False, False), (1, 2, '#0a3069', False, False)]
    (line,) = highlight.assemble('<&', toks, FG)
    assert line == '<span style="color:#0a3069">&lt;&amp;</span>'


def test_spans_never_cross_a_line_break_and_line_count_matches():
    text = '"a\nb"\n\nz'
    toks = [(0, 5, '#0a3069', False, False)]
    lines = highlight.assemble(text, toks, FG)
    assert len(lines) == text.count('\n') + 1
    assert lines == ['<span style="color:#0a3069">&quot;a</span>'.replace('&quot;', '"'),
                     '<span style="color:#0a3069">b"</span>', '', 'z']


def test_overlapping_or_empty_tokens_do_not_duplicate_text():
    toks = [(0, 3, '#cf222e', False, False), (2, 2, '#0550ae', False, False),
            (1, 5, '#0550ae', False, False)]
    (line,) = highlight.assemble('abcde', toks, FG)
    import re
    assert re.sub(r'<[^>]+>', '', line) == 'abcde'
