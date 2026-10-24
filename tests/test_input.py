# -*- coding: utf-8 -*-
from mdgh.input import (ClickJudge, scroll_target, text_command_action,
                        window_command_action)

E = 'mdgh:e:5'


def test_double_click_boundary():
    j = ClickJudge(0.5)
    assert j.feed(E, 10.0) == 'edit_first'
    assert j.feed(E, 10.5) == 'edit_double'
    j = ClickJudge(0.5)
    j.feed(E, 10.0)
    assert j.feed(E, 10.51) == 'edit_first'


def test_third_click_starts_over():
    j = ClickJudge()
    j.feed(E, 0.0)
    assert j.feed(E, 0.2) == 'edit_double'
    assert j.feed(E, 0.3) == 'edit_first'


def test_different_href_resets():
    j = ClickJudge()
    j.feed('mdgh:e:1', 0.0)
    assert j.feed('mdgh:e:2', 0.1) == 'edit_first'
    assert j.feed('mdgh:e:1', 0.2) == 'edit_first'


def test_real_link_open_then_ignore():
    j = ClickJudge()
    assert j.feed('http://x', 0.0) == 'open'
    assert j.feed('http://x', 0.2) == 'ignore'
    assert j.feed('http://x', 0.4) == 'ignore'
    assert j.feed('http://x', 0.6) == 'open'  # 첫 클릭 기준 interval 경과
    assert j.feed('http://y', 0.7) == 'open'


def test_text_command_classes():
    assert text_command_action('drag_select', None) == 'block'
    assert text_command_action('fold_tag_attributes', None) == 'block'
    assert text_command_action('insert', {}) == 'hint'
    assert text_command_action('cut', {}) == 'hint'
    assert text_command_action('move', {'by': 'lines', 'forward': True}) == 'scroll'
    assert text_command_action('move_to', {'to': 'eof'}) == 'scroll'
    assert text_command_action('find_next', None) == 'edit_then_run'
    assert text_command_action('find_under', None) == 'edit_then_run'
    assert text_command_action('copy', None) is None


KW = dict(y=500, line_h=20, viewport_h=800, max_y=1000)


def test_scroll_targets():
    assert scroll_target('move', {'by': 'lines', 'forward': True}, **KW) == 520
    assert scroll_target('move', {'by': 'lines', 'forward': False}, **KW) == 480
    kw = dict(KW, y=100)
    assert scroll_target('move', {'by': 'pages', 'forward': True}, **kw) == 100 + 780
    assert scroll_target('move', {'by': 'pages', 'forward': False}, **dict(KW, y=900)) == 120
    assert scroll_target('move_to', {'to': 'bof'}, **KW) == 0
    assert scroll_target('move_to', {'to': 'eof'}, **KW) == 1000


def test_scroll_clamped_and_none():
    kw = dict(KW, y=990)
    assert scroll_target('move', {'by': 'pages', 'forward': True}, **kw) == 1000
    kw = dict(KW, y=5)
    assert scroll_target('move', {'by': 'lines', 'forward': False}, **kw) == 0
    assert scroll_target('move_to', {'to': 'bol'}, **KW) == 0
    assert scroll_target('move_to', {'to': 'eol'}, **KW) == 1000
    assert scroll_target('move', {'by': 'characters', 'forward': True}, **KW) is None
    assert scroll_target('move', None, **KW) is None
    assert scroll_target('insert', {}, **KW) is None


def test_window_commands():
    for p in ('find', 'replace', 'incremental_find'):
        assert window_command_action('show_panel', {'panel': p}) == 'edit_then_run'
    assert window_command_action('show_panel', {'panel': 'console'}) == 'pass'
    assert window_command_action('show_panel', None) == 'pass'
    g = lambda t, ph=1: window_command_action('show_overlay', {'overlay': 'goto', 'text': t}, ph)
    assert g(':12') == 'edit_then_run'
    assert g('#head') == 'edit_then_run'
    assert g('@sym') == 'edit_then_run'
    assert g('@sym', 2) == 'heading_panel'
    assert g('') == 'pass'
    assert g('abc') == 'pass'
    assert window_command_action('show_overlay', {'overlay': 'command_palette', 'text': ':'}) == 'pass'
    assert window_command_action('show_overlay', {'overlay': 'goto'}) == 'pass'
