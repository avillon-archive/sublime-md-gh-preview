# -*- coding: utf-8 -*-
import os

from mdgh.modestore import ModeStore


def test_put_get_survives_reload(tmp_path):
    p = str(tmp_path / 'sub' / 'modes.json')
    s = ModeStore(p)
    s.put(str(tmp_path / 'a.md'), 42, now=100.0)
    s2 = ModeStore(p)
    assert s2.get(str(tmp_path / 'a.md')) == {'line': 42, 'time': 100.0}
    assert s2.get(str(tmp_path / 'b.md')) is None


def test_path_normalization(tmp_path):
    s = ModeStore(str(tmp_path / 'm.json'))
    s.put(str(tmp_path / 'x' / '..' / 'a.md'), 3, now=1.0)
    assert s.get(str(tmp_path / 'a.md'))['line'] == 3
    if os.name == 'nt':
        assert s.get(str(tmp_path / 'A.MD'))['line'] == 3
    else:
        assert s.get(str(tmp_path / 'A.MD')) is None


def test_remove_persists(tmp_path):
    p = str(tmp_path / 'm.json')
    s = ModeStore(p)
    s.put('a.md', 1, now=1.0)
    s.remove('a.md')
    s.remove('never.md')
    assert ModeStore(p).get('a.md') is None


def test_limit_evicts_oldest(tmp_path):
    p = str(tmp_path / 'm.json')
    s = ModeStore(p, limit=3)
    for i in range(5):
        s.put('f%d.md' % i, i, now=float(i))
    s = ModeStore(p, limit=3)
    assert [s.get('f%d.md' % i) is not None for i in range(5)] == [False, False, True, True, True]


def test_put_existing_refreshes_age(tmp_path):
    s = ModeStore(str(tmp_path / 'm.json'), limit=2)
    s.put('a.md', 1, now=1.0)
    s.put('b.md', 1, now=2.0)
    s.put('a.md', 9, now=3.0)
    s.put('c.md', 1, now=4.0)
    assert s.get('b.md') is None
    assert s.get('a.md')['line'] == 9


def test_broken_file_starts_empty(tmp_path):
    p = tmp_path / 'm.json'
    p.write_text('{not json', encoding='utf-8')
    s = ModeStore(str(p))
    assert s.get('a.md') is None
    s.put('a.md', 5, now=1.0)
    assert ModeStore(str(p)).get('a.md')['line'] == 5


def test_wrong_shape_entries_dropped(tmp_path):
    p = tmp_path / 'm.json'
    p.write_text('{"x": 1, "y": {"line": "a"}}', encoding='utf-8')
    s = ModeStore(str(p))
    assert s.get('x') is None and s.get('y') is None
    p.write_text('[1,2]', encoding='utf-8')
    assert ModeStore(str(p)).get('x') is None
