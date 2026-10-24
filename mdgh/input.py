# -*- coding: utf-8 -*-
EDIT_PREFIX = 'mdgh:e:'

BLOCKED_TEXT_COMMANDS = frozenset({
    'drag_select', 'select_all',
    'undo', 'redo', 'redo_or_repeat', 'soft_undo', 'soft_redo',
    'fold', 'unfold', 'unfold_all', 'fold_by_level', 'fold_tag_attributes',
})

HINT_TEXT_COMMANDS = frozenset({
    'insert', 'insert_snippet', 'paste', 'paste_and_indent', 'paste_from_history',
    'left_delete', 'right_delete', 'delete_word', 'delete_to_mark', 'cut',
    'indent', 'unindent', 'insert_best_completion', 'duplicate_line',
    'swap_line_up', 'swap_line_down', 'join_lines', 'transpose',
})

# Searches in the folded source would unfold it; they run on the source after leaving the preview.
EDIT_TEXT_COMMANDS = frozenset({
    'find_next', 'find_prev', 'find_under', 'find_under_prev', 'find_under_expand',
    'find_under_expand_skip', 'find_all_under',
})

_FIND_PANELS = frozenset({'find', 'replace', 'incremental_find'})


class ClickJudge:
    def __init__(self, interval=0.5):
        self._interval = interval
        self._href = None
        self._time = 0.0

    def feed(self, href, now):
        is_edit = href.startswith(EDIT_PREFIX)
        if not (href == self._href and now - self._time <= self._interval):
            # 다른 href 이거나 interval 을 넘겼으면 새로 시작한다.
            self._href, self._time = href, now
            return 'edit_first' if is_edit else 'open'
        if is_edit:
            self._href = None
            return 'edit_double'
        return 'ignore'  # 첫 클릭 시각을 유지해 반복 클릭이 창을 늘리지 않게 한다.


def text_command_action(name, args):
    if name in BLOCKED_TEXT_COMMANDS:
        return 'block'
    if name in HINT_TEXT_COMMANDS:
        return 'hint'
    if name in EDIT_TEXT_COMMANDS:
        return 'edit_then_run'
    if name in ('move', 'move_to'):
        return 'scroll'
    return None


def scroll_target(name, args, *, y, line_h, viewport_h, max_y):
    args = args or {}
    if name == 'move':
        by = args.get('by')
        if by not in ('lines', 'pages') or 'forward' not in args:
            return None
        step = line_h if by == 'lines' else viewport_h - line_h
        target = y + (step if args['forward'] else -step)
    elif name == 'move_to':
        to = args.get('to')
        # Home/End(bol/eol)도 미리보기에는 줄이 없으므로 맨 위·맨 아래로 보낸다.
        if to in ('bof', 'bol', 'hardbol'):
            target = 0
        elif to in ('eof', 'eol', 'hardeol'):
            target = max_y
        else:
            return None
    else:
        return None
    return float(min(max(target, 0), max_y))


def window_command_action(name, args, phase=1):
    args = args or {}
    if name == 'show_panel' and args.get('panel') in _FIND_PANELS:
        return 'edit_then_run'
    if name == 'show_overlay' and args.get('overlay') == 'goto':
        text = args.get('text') or ''
        if text[:1] in (':', '#'):
            return 'edit_then_run'
        if text[:1] == '@':
            return 'heading_panel' if phase >= 2 else 'edit_then_run'
    return 'pass'
