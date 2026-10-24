# -*- coding: utf-8 -*-
import json
import os
import re

import pytest

from mdgh import theme

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


@pytest.fixture
def light():
    return theme.load_vars(read('themes', 'github-light.json'))


def css(vars, body_px=16.0, h_body=21.0, h_mono=16.0, user=()):
    return theme.build_css(vars, read('themes', 'base.css'), body_px=body_px, font_body='Segoe UI',
                           font_mono='Consolas', h_body=h_body, h_mono=h_mono, user_css=list(user))


def length_of(text, selector, prop):
    # the first rule whose selector list names `selector` and sets `prop` to a px length
    for sels, body in re.findall(r'(?m)^([^{}\n]+) \{([^}]*)\}', text):
        if selector in sels.split(', '):
            m = re.search(r'\b%s: ([\d.]+)px' % prop, body)
            if m:
                return float(m.group(1))
    raise AssertionError('no %s with %s' % (selector, prop))


@pytest.mark.parametrize('p,h,expected', [(24, 20, 28), (22.5, 21, 24), (24, 24, None), (20, 24, None)])
def test_line_height_css_reaches_target_when_larger_than_natural(p, h, expected):
    assert theme.line_height_css(p, h) == expected


def test_theme_file_has_source_and_derived_vertical_border(light):
    assert 'github-markdown-css v' in light['_source']
    c = light['colors']
    assert c['table-border-v'] != c['table-border']
    assert re.fullmatch(r'#[0-9a-f]{6}', c['table-border-v'])


def test_load_vars_rejects_incomplete_theme():
    with pytest.raises(ValueError):
        theme.load_vars(json.dumps({'name': 'x'}))


@pytest.mark.parametrize('name,other', [('github-light', 'github-dark'), ('github-dark', 'github-light')])
def test_css_has_no_unresolved_placeholders_and_forbidden_constructs(name, other):
    v = theme.load_vars(read('themes', name + '.json'))
    out = css(v)
    assert v['colors']['fg'] in out
    assert theme.load_vars(read('themes', other + '.json'))['colors']['fg'] not in out
    assert not re.search(r'\{(c|px|lh)\.|\{font_', out)
    assert '<style' not in out
    assert "'" not in out
    # var() is only usable as a whole declaration value in minihtml
    for decl in re.findall(r'[\w-]+:[^;{}]*var\([^;{}]*', out):
        assert re.fullmatch(r'[\w-]+: var\(--[\w-]+\)', decl), decl
    used = set(re.findall(r'var\((--[\w-]+)\)', out))
    defined = set(re.findall(r'(--[\w-]+):', out))
    assert used <= defined


def test_lengths_scale_with_body_px(light):
    small, big = css(light, 16.0), css(light, 32.0)
    for sel, prop in (('h1', 'font-size'), ('ul', 'padding-left'), ('.pre', 'font-size')):
        assert length_of(big, sel, prop) == pytest.approx(2 * length_of(small, sel, prop), abs=0.02)
    assert length_of(small, 'h1', 'font-size') == 32


def test_block_gap_leaves_room_for_phantom_padding(light):
    # ST adds 4px to every block phantom; the wrapper supplies the remainder of 16px.
    assert length_of(css(light, 16.0), '.blk', 'padding-bottom') == 12
    assert length_of(css(light, 32.0), '.blk', 'padding-bottom') == 28
    assert length_of(css(light, 16.0), '.k-heading', 'padding-top') == 8


def test_line_height_declarations_follow_measured_heights(light):
    out = css(light, 16.0, h_body=21.0, h_mono=14.0)
    assert re.search(r'p, li, \.oi, \.t \{ line-height: 27px; \}', out)       # 2*24 - 21
    assert re.search(r'line-height: 25\.44px;', out)                          # 2*(1.45*13.6) - 14
    flat = css(light, 16.0, h_body=40.0, h_mono=40.0)
    # only the fixed line-heights remain: code and .del (minihtml draws an inline background or
    # border at the inherited paragraph line-height, so the box overlaps the next line and the
    # strike line drops to the baseline) and the image span (it stops minihtml stretching images)
    assert re.findall(r'(\S+) \{[^}]*line-height', flat) == ['code', '.im', '.del']


def test_fonts_are_double_quoted_and_user_css_comes_last(light):
    out = css(light, user=['.x { color: red; }', '.y { color: blue; }'])
    assert 'font-family: "Segoe UI",' in out and 'font-family: "Consolas",' in out
    assert out.endswith('.x { color: red; }\n.y { color: blue; }')
    assert theme.css_digest(['.x']) != theme.css_digest(['.y']) != theme.css_digest([])


@pytest.mark.parametrize('name', ['github-light', 'github-dark'])
def test_scheme_has_globals_only_and_hides_text_colors(name):
    v = theme.load_vars(read('themes', name + '.json'))
    scheme = theme.build_scheme(v, 'html { }')
    g = scheme['globals']
    assert scheme['rules'] == [] and g['phantom_css'] == 'html { }'
    bg = v['colors']['bg']
    assert g['background'] == bg
    for k in ('foreground', 'caret', 'selection', 'fold_marker', 'line_highlight'):
        assert g[k] == bg
    json.dumps(scheme)


def test_scheme_file_name_is_stable_and_tracks_content(light):
    a = theme.build_scheme(light, 'html { a: 1; }')
    b = theme.build_scheme(light, 'html { a: 2; }')
    n1, n2 = theme.scheme_file_name('github-light', a), theme.scheme_file_name('github-light', b)
    assert n1 == theme.scheme_file_name('github-light', json.loads(json.dumps(a)))
    assert n1 != n2
    assert re.fullmatch(r'github-light-[0-9a-f]+\.hidden-color-scheme', n1)


def test_stale_schemes_never_deletes_keep_even_when_oldest():
    entries = [('ref', 1), ('a', 5), ('b', 6)]
    assert theme.stale_schemes(entries, {'ref'}, 1) == ['a']


def test_stale_schemes_keeps_newest_non_keep_by_mtime():
    entries = [('n%d' % i, i) for i in range(10)] + [('ref', 100)]
    stale = theme.stale_schemes(entries, {'ref'}, 3)
    assert sorted(stale) == ['n%d' % i for i in range(7)]


def test_stale_schemes_bounds_and_tie_order():
    entries = [('a', 1), ('b', 1), ('c', 1)]
    assert theme.stale_schemes(entries, set(), 0) == ['c', 'b', 'a']
    assert theme.stale_schemes(entries, set(), 3) == []
    assert theme.stale_schemes(entries, set(), 2) == ['a']


def test_body_px_is_github_size_times_font_scale():
    assert theme.body_px(1.0) == pytest.approx(16)
    assert theme.body_px(1.25) == pytest.approx(20)


def test_zoom_returns_exactly_to_the_scale_of_a_font_size():
    anchor, s, fs = None, 1.0, 15
    for step in [1, 1, 1, -1, 1, -1, -1, -1, -1, -1, 1, 1, 1, 1, -1, -1, -1, 1, -1]:
        anchor, s = theme.zoom_scale(anchor, s, fs, fs + step)
        fs += step
        assert s == round(fs / 15, 4)
    assert (fs, s) == (14, round(14 / 15, 4))


def test_zoom_restarts_from_a_hand_edited_scale():
    anchor, s = theme.zoom_scale(None, 1.0, 15, 16)
    anchor, s = theme.zoom_scale(anchor, 1.2, 16, 17)       # font_scale edited by hand to 1.2
    assert anchor == (16, 1.2) and s == round(1.2 * 17 / 16, 4)


# ---------------------------------------------------------------- dark theme, user CSS, icons


@pytest.fixture
def dark():
    return theme.load_vars(read('themes', 'github-dark.json'))


def _keys(v):
    return {k: sorted(v[k]) if isinstance(v[k], dict) else None for k in v}


def test_dark_theme_mirrors_light_structure_and_source(light, dark):
    assert _keys(dark) == _keys(light)
    assert dark['kind'] == 'dark' and light['kind'] == 'light'
    # Same github-markdown-css release for both files.
    ver = re.search(r'v[\d.]+', light['_source']).group(0)
    assert ver in dark['_source'] and 'dark' in dark['_source']
    assert dark['px'] == light['px'] and dark['lh'] == light['lh']


@pytest.mark.parametrize('name', ['github-light', 'github-dark'])
def test_theme_brightness_matches_its_kind(name):
    v = theme.load_vars(read('themes', name + '.json'))
    assert theme.is_dark(v['colors']['bg']) == (v['kind'] == 'dark')
    assert theme.is_dark(v['colors']['fg']) != theme.is_dark(v['colors']['bg'])
    assert theme.theme_name(v['kind']) == v['name'] == name


def test_setting_kind_and_brightness():
    assert theme.setting_kind('github-dark') == 'dark'
    assert theme.setting_kind('github-light') == 'light'
    assert theme.setting_kind('auto') is None
    assert theme.is_dark('#303841') and theme.is_dark('#000') and theme.is_dark('#0d1117ff')
    assert not theme.is_dark('#ffffff') and not theme.is_dark('#fbffff')


def test_collect_user_css_keeps_order_and_skips_missing():
    files = {'Packages/User/a.css': 'A', 'C:/x/b.css': 'B'}

    def load(p):
        if p not in files:
            raise FileNotFoundError(p)
        return files[p]
    texts, missing = theme.collect_user_css(
        ['C:/x/b.css', 'C:/nope.css', 'Packages/User/a.css', ''], load)
    assert texts == ['B', 'A']
    assert missing == ['C:/nope.css']


def test_icon_html_uses_only_allowed_markup():
    from mdgh import render
    out = theme.icon_html('alert-note', 'dark', 16.4, 'style="padding-right: 5px"')
    tags = re.findall(r'<\s*(\w+)', out)
    assert tags == ['img'] and set(tags) <= render.ALLOWED_TAGS
    attrs = dict(re.findall(r'(\w[\w-]*)="([^"]*)"', out))
    assert set(attrs) <= {'src', 'width', 'height', 'style', 'title', 'alt'}
    assert attrs['width'] == attrs['height'] == '16'
    for decl in attrs['style'].split(';'):
        if decl.strip():
            assert decl.split(':')[0].strip() in render.ALLOWED_CSS_PROPS
    with pytest.raises(ValueError):
        theme.icon_html('nope', 'light', 16)
    with pytest.raises(ValueError):
        theme.icon_html('edit', 'sepia', 16)


@pytest.mark.parametrize('kind', ['light', 'dark'])
@pytest.mark.parametrize('name', theme.ICON_NAMES)
def test_icon_src_points_at_a_double_size_png(name, kind):
    pytest.importorskip('PIL')
    from PIL import Image
    out = theme.icon_html(name, kind, 16)
    src = re.search(r'src="([^"]+)"', out).group(1)
    prefix = 'res://' + theme.resource_path('')
    assert src.startswith(prefix)
    path = os.path.join(ROOT, *src[len(prefix):].split('/'))
    with Image.open(path) as im:
        assert im.size == (32, 32) and im.mode == 'RGBA'
        assert im.getchannel('A').getextrema()[1] == 255
