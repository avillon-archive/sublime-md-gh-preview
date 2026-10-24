# -*- coding: utf-8 -*-
import random

import pytest

from mdgh import blocks, layout


# ---- layout A/B choice: A only when line 1 and the button share a display line


@pytest.mark.parametrize('line1_w,button_w,expected', [
    (0, 60, 'A'),          # empty line 1 (file starts with a blank line)
    (500, 60, 'A'),
    (1000 - 60 - 24, 60, 'A'),       # exactly fits with the margin
    (1000 - 60 - 24 + 1, 60, 'B'),   # one pixel too wide for the button
    (5000, 60, 'B'),       # line 1 wraps
    (976, 0, 'A'),         # no button: the margin is still needed
    (977, 0, 'B'),
])
def test_choose_layout_requires_room_for_button(line1_w, button_w, expected):
    assert layout.choose_layout(line1_w, 1000, button_w) == expected


# ---- fold span


def test_fold_span_b_keeps_only_first_character():
    assert layout.fold_span('B', 500, 120) == (1, 500)


def test_fold_span_b_one_character_document_has_nothing_to_fold():
    assert layout.fold_span('B', 1, 0) is None


def test_fold_span_a_starts_after_the_anchor_line():
    text = '# Title\n\nbody\n'
    end = text.index('\n')
    assert layout.fold_span('A', len(text), end) == (end + 1, len(text))


def test_fold_span_a_single_line_document_folds_nothing():
    assert layout.fold_span('A', 5, 5) is None
    # trailing newline only: the empty line 2 is left, nothing to fold
    assert layout.fold_span('A', 6, 5) is None


# ---- edit-mode button padding


def test_edit_button_pad_fits_on_line1():
    pad, wraps = layout.edit_button_pad(1000, 300, 60)
    assert not wraps
    assert pad == 616


def test_edit_button_pad_wraps_to_next_display_line_when_no_room():
    pad, wraps = layout.edit_button_pad(1000, 950, 60)
    assert wraps
    # placed from x 0 on its own display line, still right-aligned
    assert pad == 916


def test_edit_button_pad_never_negative_in_tiny_viewport():
    assert layout.edit_button_pad(50, 40, 60) == (0, True)


def test_toolbar_b_pad_leaves_room_for_first_char_and_marker():
    pad = layout.toolbar_b_pad(1000, 60, 9, 24)
    assert pad == 883
    assert layout.toolbar_b_pad(50, 60, 9, 24) == 0


# ---- text area width


def test_text_area_width_uses_wrap_width_only_when_narrower():
    assert layout.text_area_width(1000, 8, True, 80) == 640
    assert layout.text_area_width(500, 8, True, 80) == 500
    assert layout.text_area_width(1000, 8, False, 80) == 1000
    assert layout.text_area_width(1000, 8, True, 0) == 1000


# ---- incremental redraw start


def _ids(text):
    # the controller's block identity: (html_key, is first block)
    return [(b.html_key, b.index == 0) for b in blocks.parse(text).blocks]


DOC = '# A\n\npara one\n\npara two\n\n## B\n\nlast\n'


def test_first_diff_edit_in_middle_redraws_from_that_block():
    new = DOC.replace('para two', 'para 2')
    assert layout.first_diff(_ids(DOC), _ids(new)) == 2


def test_first_diff_append_keeps_every_existing_block():
    old = _ids(DOC)
    assert layout.first_diff(old, _ids(DOC + '\nmore\n')) == len(old)


def test_first_diff_truncation():
    assert layout.first_diff([1, 2, 3], [1, 2]) == 2


# ---- measured line breaking


def _random_tokens(rng, n):
    widths, kinds = [], []
    for _ in range(n):
        k = rng.choice('wwwwsn' if rng.random() < 0.1 else 'wwws')
        kinds.append(k)
        widths.append({'w': rng.randint(1, 120), 's': rng.randint(3, 6), 'n': 0}[k])
    return widths, kinds


def test_wrap_tokens_never_exceeds_max_width_unless_a_line_is_one_token():
    rng = random.Random(7)
    for _ in range(500):
        widths, kinds = _random_tokens(rng, rng.randint(0, 40))
        maxw = rng.randint(20, 300)
        lines = layout.wrap_tokens(widths, kinds, maxw)
        seen = [i for line in lines for i in line]
        assert seen == sorted(seen)
        # every word is placed exactly once
        assert [i for i in seen if kinds[i] == 'w'] == [i for i, k in enumerate(kinds) if k == 'w']
        for line in lines:
            if line:
                assert kinds[line[0]] == 'w' and kinds[line[-1]] == 'w'
            if len(line) > 1:
                assert sum(widths[i] for i in line) <= maxw


def test_wrap_tokens_breaks_at_forced_breaks_and_fills_greedily():
    w = [30, 5, 30, 5, 30, 0, 30]
    k = ['w', 's', 'w', 's', 'w', 'n', 'w']
    assert layout.wrap_tokens(w, k, 65) == [[0, 1, 2], [4], [6]]
    assert layout.wrap_tokens(w, k, 1000) == [[0, 1, 2, 3, 4], [6]]
    assert layout.wrap_tokens([], [], 10) == [[]]
    assert layout.wrap_tokens([50], ['w'], 10) == [[0]]     # a single word may overflow


# ---- table column caps


def test_column_caps_keep_natural_widths_when_the_table_fits():
    assert layout.column_caps([100, 50, 30], [20, 10, 5], 180) == [100, 50, 30]


def test_column_caps_respect_budget_and_word_minimum():
    rng = random.Random(11)
    for _ in range(500):
        n = rng.randint(1, 10)
        minw = [rng.randint(0, 80) for _ in range(n)]
        nat = [m + rng.randint(0, 600) for m in minw]
        budget = rng.randint(sum(minw), sum(nat) + 50)
        caps = layout.column_caps(nat, minw, budget)
        assert sum(caps) <= budget
        assert all(m <= c <= x for c, m, x in zip(caps, minw, nat))
        if sum(nat) > budget:
            # the cap is the largest whole px that fits: one px more would not
            cap = max(c for c, m in zip(caps, minw) if c > m) if any(c > m for c, m in zip(caps, minw)) else 0
            over = sum(max(m, min(x, cap + 1)) for m, x in zip(minw, nat))
            assert over > budget


def test_column_caps_fall_back_to_word_minimum_when_nothing_fits():
    assert layout.column_caps([300, 300], [90, 120], 100) == [90, 120]


def test_table_budget_takes_out_padding_borders_and_safety_per_column():
    one = layout.table_budget(1000, 1, 13)
    two = layout.table_budget(1000, 2, 13)
    assert one - two == 2 * 13 + 1 + layout.SAFETY
    assert one < 1000 - 2 * 13


# ---- alignment and list markers


@pytest.mark.parametrize('align', ['left', 'right', 'center'])
def test_align_pads_fill_the_column(align):
    pl, pr = layout.align_pads(align, 100, 37)
    if align == 'left':
        assert (pl, pr) == (0, 0)
    else:
        assert pl + pr == 63 and (pr == 0 if align == 'right' else abs(pl - pr) <= 1)


def test_marker_pads_put_the_text_at_the_indent():
    for mw in (0, 7, 15, 28):
        pl, pr = layout.marker_pads(32, mw, 4)
        assert pl + mw + pr == 32 and pr >= 4
    pl, pr = layout.marker_pads(32, 60, 4)      # a marker wider than the indent pushes the text
    assert pl == 0 and pr == 0
