# -*- coding: utf-8 -*-
import dataclasses
import os
import re
from html.parser import HTMLParser

import pytest

from mdgh import blocks, layout, render, theme

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, 'tests', 'fixtures', 'sample.md')
with open(os.path.join(ROOT, 'themes', 'github-light.json'), encoding='utf-8') as _f:
    METRICS = theme.layout_metrics(theme.load_vars(_f.read()), 16)
FONTS = ('Segoe UI', 'Consolas')
CTX = render.RenderContext(body_px=16, pad_left=12, pad_right=34, theme='light', avail=600,
                           metrics=METRICS, fonts=FONTS)
CHAR_EM = {'body': 0.5, 'bold': 0.56, 'mono': 0.6}


def fake_measure(kind, px, texts):
    """Stand-in for the ST panels: whole px proportional to the character count."""
    assert kind in layout.FONT_KINDS
    return [float(round(len(t) * CHAR_EM[kind] * px)) for t in texts]

DOC_A = (
    '# Title\n\npara one\nsoft line  \nhard line\n\n- a\n- b\n  - c\n\n> q1\n> q2\n\n'
    '```py\nx = 1\n\ny = 2\n```\n\n    ind1\n\n    ind2\n'
)
ROWS_A = {0, 2, 3, 4, 6, 7, 8, 10, 11, 14, 15, 16, 19, 20, 21}

DOC_B = (
    '---\ntitle: x\n---\n\n| a | b |\n|---|---|\n| `c` | **d** |\n\n> [!WARNING]\n> careful\n\n'
    '3. three\n4. four\n\n- [ ] todo\n- [x] done\n\ntext[^n] more\n\n[^n]: the note\n\n'
    '<!-- gone -->\n\nafter <!-- inline gone --> end\n'
)
ROWS_B = {1, 4, 6, 8, 9, 11, 12, 14, 15, 17, 19, 23}


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.styles = []
        self.anchors = []      # (row, text)
        self.text = []
        self.nested_a = False
        self._a_depth = 0
        self._cur = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        a = dict(attrs)
        if 'style' in a:
            self.styles.append(a['style'])
        if tag == 'a':
            self._a_depth += 1
            self.nested_a |= self._a_depth > 1
            if a.get('class') == 'e':
                self._cur = [int(a['href'].split(':')[-1]), '']

    def handle_endtag(self, tag):
        if tag == 'a':
            self._a_depth -= 1
            if self._cur is not None:
                self.anchors.append(tuple(self._cur))
                self._cur = None

    def handle_data(self, data):
        self.text.append(data)
        if self._cur is not None:
            self._cur[1] += data


def render_all(text, ctx=CTX):
    doc = blocks.parse(text)
    return doc, [render.render_block(b, doc, ctx, fake_measure) for b in doc.blocks]


def pages(text):
    doc, outs = render_all(text)
    return doc, [Page(o) for o in outs]


def check_anchor_texts(text, anchors):
    src = text.replace('\r\n', '\n').split('\n')
    for row, t in anchors:
        t = t.replace(' ', ' ')   # code spans keep their spaces as no-break spaces
        if re.fullmatch(r'\[(\d+|image)\]|Note|Tip|Important|Warning|Caution', t.strip()) \
                and t.strip().lower() not in src[row].lower():
            continue
        assert t.strip().lower() in src[row].lower(), (row, t, src[row])


@pytest.mark.parametrize('text,rows', [(DOC_A, ROWS_A), (DOC_B, ROWS_B)])
def test_edit_links_cover_every_text_line_with_its_own_row(text, rows):
    doc, ps = pages(text)
    covered = set()
    for b, p in zip(doc.blocks, ps):
        check_anchor_texts(text, p.anchors)
        for row, _ in p.anchors:
            covered.add(row)
            if b.kind != 'footnotes':
                assert b.map_start <= row < b.map_end
    assert covered == rows


def test_real_links_are_not_wrapped_and_anchors_never_nest():
    doc, ps = pages('see [the **doc** page](http://x.test/a) and <http://y.test> now\n')
    p = ps[0]
    assert not p.nested_a
    assert [t.strip() for _, t in p.anchors] == ['see', 'and', 'now']
    assert 'href="http://x.test/a"' in render.render_block(doc.blocks[0], doc, CTX, fake_measure)


def test_inline_html_comments_are_hidden():
    _, outs = render_all('shown <!-- hidden --> text\n')
    assert 'hidden' not in ''.join(outs)


def test_strikethrough_uses_border_spans_not_line_through():
    out = render_all('~~gone~~\n')[1][0]
    assert out.count('class="del"') == 1 and 'line-through' not in out


def test_wrapper_classes_and_padding():
    doc, outs = render_all('# h\n\ntext\n')
    first, second = outs
    assert first.startswith('<body id="mdgh"><div class="blk k-heading first" ')
    assert 'padding-left:12px;padding-right:34px' in first
    assert 'class="blk k-paragraph"' in second and 'first' not in second.split('>')[1]


def test_empty_document_block():
    out = render.render_empty(CTX)
    assert 'Empty document' in out and 'first' in out


def test_context_key_changes_with_every_field():
    base = dict(body_px=16, pad_left=12, pad_right=34, theme='light', avail=600, metrics=METRICS,
                fonts=FONTS, doc_dir='doc')
    fields = [f.name for f in dataclasses.fields(render.RenderContext)]
    assert set(base) == set(fields)       # a new field must get a base value here

    def changed(v):
        return v + 1 if isinstance(v, (int, float)) else v + ('x',) if isinstance(v, tuple) else v + 'x'
    keys = {render.RenderContext(**base).key()}
    keys |= {render.RenderContext(**dict(base, **{n: changed(base[n])})).key() for n in fields}
    assert len(keys) == len(fields) + 1


def assert_within_allow_lists(outs):
    for out in outs:
        assert '<style' not in out
        p = Page(out)
        assert set(p.tags) <= render.ALLOWED_TAGS, set(p.tags) - render.ALLOWED_TAGS
        for style in p.styles:
            assert 'font-family' not in style and "'" not in style
            for decl in filter(None, (d.strip() for d in style.split(';'))):
                assert decl.split(':')[0].strip() in render.ALLOWED_CSS_PROPS, decl


def test_sample_renders_inside_allow_lists_with_valid_rows():
    with open(SAMPLE, encoding='utf-8') as f:
        text = f.read()
    doc, outs = render_all(text)
    assert len(outs) > 10
    assert_within_allow_lists(outs)
    for b, out in zip(doc.blocks, outs):
        p = Page(out)
        check_anchor_texts(text, p.anchors)
        assert all(b.map_start <= r < b.map_end for r, _ in p.anchors)


# ---------------------------------------------------------------- measured layout (tables, lists)


class Node:
    def __init__(self, tag, attrs):
        self.tag, self.attrs, self.children, self.text = tag, dict(attrs), [], ''

    @property
    def cls(self):
        return set((self.attrs.get('class') or '').split())

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def find(self, tag=None, cls=None):
        return [n for n in self.walk() if (tag is None or n.tag == tag)
                and (cls is None or cls in n.cls)]

    def style(self):
        out = {}
        for d in filter(None, (x.strip() for x in (self.attrs.get('style') or '').split(';'))):
            k, v = d.split(':')
            out[k.strip()] = float(v.strip()[:-2])
        return out


class Tree(HTMLParser):
    VOID = {'img', 'br'}

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = Node('root', [])
        self.stack = [self.root]
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs)
        self.stack[-1].children.append(n)
        if tag not in self.VOID:
            self.stack.append(n)

    def handle_endtag(self, tag):
        if tag not in self.VOID:
            assert self.stack.pop().tag == tag

    def handle_data(self, data):
        n = Node('#text', [])
        n.text = data
        self.stack[-1].children.append(n)


M = dict(METRICS)
WIDE_TABLE = (
    'intro\n\n'
    '| name | mid | num |\n|:-----|:---:|----:|\n'
    '| alpha beta gamma delta epsilon zeta eta theta iota kappa lambda | `code span` x | 1 |\n'
    '| **bold words here** and plain text that keeps going on | ~~old~~ [link](http://l.test) | 22 |\n'
    '| short | c | 333 |\n'
    '| last row text | *it* | 4444 |\n'
)
TABLE_ROWS = {2, 4, 5, 6, 7}


def ctx_at(avail, kind='light'):
    return render.RenderContext(16, 12, 34, kind, avail=avail, metrics=METRICS, fonts=FONTS)


def table_tree(text=WIDE_TABLE, avail=420):
    doc, outs = render_all(text, ctx_at(avail))
    k = [b.kind for b in doc.blocks].index('table')
    return Tree(outs[k]).root, outs[k]


def spacer_widths(row):
    return [int(cell.find('img')[0].attrs['width']) for cell in row.find('span', 'td')]


def test_table_columns_share_one_width_per_column_and_fit_the_budget():
    root, _ = table_tree()
    cols = [spacer_widths(r) for r in root.find('div', 'tr')]
    assert len(cols) == 5 and all(len(r) == 3 for r in cols)
    assert all(r == cols[0] for r in cols)     # every row forces the same column widths
    total = sum(w + 2 * M['cell_px'] + 1 for w in cols[0]) + 1
    assert total <= 420


def test_table_wraps_cells_and_pads_every_cell_of_a_row_to_the_same_line_count():
    root, _ = table_tree()
    counts = [[len(cell.find('div', 't')) for cell in r.find('span', 'td')]
              for r in root.find('div', 'tr')]
    assert any(max(c) > 1 for c in counts)            # the narrow budget wrapped something
    assert all(len(set(c)) == 1 for c in counts)
    wide, _ = table_tree(avail=5000)
    assert all(len(cell.find('div', 't')) == 1 for cell in wide.find('span', 'td'))


def test_table_alignment_pads_lines_inside_the_column():
    root, _ = table_tree(avail=5000)
    rows = root.find('div', 'tr')
    for r in rows:
        cells = r.find('span', 'td')
        widths = spacer_widths(r)
        for ci, cell in enumerate(cells):
            for line in cell.find('div', 't'):
                st = line.style()
                pl, pr = st.get('padding-left', 0), st.get('padding-right', 0)
                assert pl + pr <= widths[ci]
                if ci == 0:
                    assert pl == pr == 0
                elif ci == 1:
                    assert abs(pl - pr) <= 1
                else:
                    assert pr == 0
    shortest = rows[1].find('span', 'td')[2].find('div', 't')[0]   # '1' in a right column
    assert shortest.style()['padding-left'] > 0


def test_table_cell_classes_borders_header_and_stripes():
    root, _ = table_tree()
    rows = root.find('div', 'tr')
    assert 'trl' in rows[-1].cls and all('trl' not in r.cls for r in rows[:-1])
    for ri, r in enumerate(rows):
        cells = r.find('span', 'td')
        assert all(('th' in c.cls) == (ri == 0) for c in cells)
        assert ['tdr' in c.cls for c in cells] == [False, False, True]
        assert all(('tdb' in c.cls) == (ri == len(rows) - 1) for c in cells)
        assert all(('st' in c.cls) == (ri in (2, 4)) for c in cells)   # 2nd and 4th body rows
        for line in r.find('div', 't'):
            assert 'strut' in line.children[0].cls
    assert root.find('div', 'tend')


def test_table_cells_keep_inline_markup_and_edit_rows():
    root, out = table_tree()
    assert root.find('code') and root.find('b') and root.find('i') and root.find('span', 'del')
    assert 'href="http://l.test"' in out
    p = Page(out)
    assert {r for r, _ in p.anchors} == TABLE_ROWS
    check_anchor_texts(WIDE_TABLE, p.anchors)
    assert not p.nested_a


LIST_DOC = (
    '3. first item with enough words to wrap over several lines in a narrow column\n'
    '   continued on a soft break line\n'
    '4. short\n'
    '\n'
    '- [x] done task\n'
    '- [ ] open task with `code` and **bold**\n'
)


def test_ordered_item_text_hangs_at_the_indent():
    _, outs = render_all(LIST_DOC, ctx_at(260))
    items = Tree(outs[0]).root.find('div', 'oi')
    assert len(items) == 2
    marks = [i.find('span', 'mk')[0] for i in items]
    assert [m.children[0].text for m in marks] == ['3.', '4.']
    for m in marks:
        st = m.style()
        mw = fake_measure('body', 16, [m.children[0].text])[0]
        assert abs(st['padding-left'] + mw + st['padding-right'] - M['indent']) <= 1
    nbr = len(items[0].find('span', 'lc')[0].find('br'))
    assert nbr >= 2                                     # wrapped over three or more lines
    assert len(marks[0].find('br')) == nbr              # the marker box has as many lines


def test_task_items_use_theme_check_icons():
    for kind in ('light', 'dark'):
        _, outs = render_all(LIST_DOC, ctx_at(260, kind))
        root = Tree(outs[1]).root
        imgs = root.find('img')
        assert [i.attrs['src'] for i in imgs] == [
            'res://' + theme.resource_path('icons/check-on-%s.png' % kind),
            'res://' + theme.resource_path('icons/check-off-%s.png' % kind)]
        for mk, img in zip(root.find('span', 'mk'), imgs):
            st = mk.style()
            assert st['padding-left'] + int(img.attrs['width']) + st['padding-right'] == M['indent']
    # a wrapped task item: the marker box carries one filler line per extra text line
    _, outs = render_all('- [ ] ' + 'word ' * 60 + '\n', ctx_at(260))
    item = Tree(outs[0]).root.find('div', 'hl')[0]
    nbr = len(item.find('span', 'lc')[0].find('br'))
    assert nbr >= 2 and len(item.find('span', 'mk')[0].find('div', 'oi')) == nbr


def test_list_edit_links_follow_soft_breaks_and_wrapped_lines():
    _, outs = render_all(LIST_DOC, ctx_at(260))
    assert {r for o in outs for r, _ in Page(o).anchors} == {0, 1, 2, 4, 5}
    for o in outs:
        check_anchor_texts(LIST_DOC, Page(o).anchors)


FOOTNOTE_DOC = 'one[^a] two[^b] again[^a]\n\n[^a]: note a\n[^b]: note b\n    more b\n'


def test_footnote_references_and_back_links():
    doc, outs = render_all(FOOTNOTE_DOC)
    para = outs[0]
    # one block per note, so a #fn-<n> link can land on the note itself
    assert [b.kind for b in doc.blocks] == ['paragraph', 'footnotes', 'footnotes']
    assert re.findall(r'href="(#fn-\d+)"', para) == ['#fn-1', '#fn-2', '#fn-1']
    assert '<span class="fnref">' in para
    assert [re.findall(r'href="(#fnref-\d+)"', o) for o in outs[1:]] == [['#fnref-1'], ['#fnref-2']]
    roots = [Tree(o).root for o in outs[1:]]
    assert [m.children[0].text for r in roots for m in r.find('span', 'mk')] == ['1.', '2.']
    # the list's rule only above the first note; no block gap between notes
    assert [bool(r.find('div', 'fnt')) for r in roots] == [True, False]
    assert all(r.find('div', 'fns') for r in roots)
    assert ['fnx' in r.find('div', 'blk')[0].cls for r in roots] == [True, False]
    notes = ''.join(outs[1:])
    assert {r for r, _ in Page(notes).anchors} == {2, 3, 4}
    check_anchor_texts(FOOTNOTE_DOC, Page(notes).anchors)


NESTED_DOC = ('- a\n  1. b\n     - c\n       > q\n- [x] d\n\n> [!TIP]\n> tip\n>\n> second\n\n'
              '# h1\n## h2\n### h3\n#### h4\n##### h5\n###### h6\n\n***\n')


@pytest.mark.parametrize('text,avail,kind', [(DOC_A, None, 'light'), (DOC_B, None, 'light'),
                                             (NESTED_DOC, None, 'light')]
                         + [(t, w, 'dark') for w in (120, 420, 5000)
                            for t in (WIDE_TABLE, LIST_DOC, FOOTNOTE_DOC)])
def test_output_stays_inside_allow_lists_for_every_construct(text, avail, kind):
    ctx = CTX if avail is None else ctx_at(avail, kind)
    assert_within_allow_lists(render_all(text, ctx)[1])


def test_measure_is_batched_per_font_and_size():
    calls = []

    def counting(kind, px, texts):
        calls.append((kind, px))
        return fake_measure(kind, px, texts)
    doc = blocks.parse(WIDE_TABLE)
    render.render_block(doc.blocks[1], doc, CTX, counting)
    # tokens first, then the laid-out lines: at most two calls per (font, size)
    assert all(calls.count(c) <= 2 for c in calls)



def fake_highlight(calls=None):
    """Colors the first word of each code line (after indentation); stands in for highlight.lines (ST panel)."""
    def hl(info, code):
        if calls is not None:
            calls.append((info, code))
        if not (info or '').strip().startswith('py'):
            return None
        out = []
        for line in code.split('\n'):
            w, sep, rest = line.lstrip().partition(' ')
            pad = line[:len(line) - len(line.lstrip())]
            out.append('%s<span style="color:#cf222e"><b>%s</b></span>%s%s' % (pad, w, sep, rest) if w else '')
        return out
    return hl


HL_DOC = 'intro\n\n```python extra\nif x:\n\n    pass\n```\n\n```\nplain\n```\n'


def render_hl(text, hl):
    doc = blocks.parse(text)
    return [render.render_block(b, doc, CTX, fake_measure, hl) for b in doc.blocks]


def test_highlighted_code_keeps_one_edit_link_per_code_line_with_fence_rows():
    outs = render_hl(HL_DOC, fake_highlight())
    p = Page(outs[1])
    assert [r for r, _ in p.anchors] == [3, 4, 5]
    assert [t.strip() for _, t in p.anchors] == ['if x:', '', 'pass']
    assert not p.nested_a
    assert 'color:#cf222e' in outs[1]
    assert_within_allow_lists(outs)


def test_highlight_receives_fence_info_and_unhighlighted_blocks_stay_plain():
    calls = []
    outs = render_hl(HL_DOC, fake_highlight(calls))
    assert calls[0] == ('python extra', 'if x:\n\n    pass')
    plain = render_hl(HL_DOC, None)
    assert outs[2] == plain[2] and 'color:' not in outs[2]


def test_highlight_result_with_wrong_line_count_falls_back_to_plain():
    outs = render_hl(HL_DOC, lambda info, code: ['only one'])
    assert outs == render_hl(HL_DOC, None)


def test_highlight_is_not_asked_for_indented_code_front_matter_or_html():
    calls = []
    render_hl('---\na: 1\n---\n\n    ind\n\n<div>x</div>\n', fake_highlight(calls))
    assert calls == []


# ---------------------------------------------------------------- alerts, images, markers, widths


ALERTS = '\n\n'.join('> [!%s]\n> body %d' % (k, i) for i, k in
                     enumerate(('NOTE', 'TIP', 'IMPORTANT', 'WARNING', 'CAUTION')))


def test_alerts_have_bar_class_icon_and_kind_title():
    for kind in ('light', 'dark'):
        doc, outs = render_all(ALERTS, ctx_at(600, kind))
        assert_within_allow_lists(outs)
        for b, out in zip(doc.blocks, outs):
            name = b.tokens[0].meta['kind'].lower()
            root = Tree(out).root
            box = root.find('div', 'al')[0]
            assert 'al-' + name in box.cls and 'bq' in box.cls
            title = root.find('div', 'alt')[0]
            img = title.children[0]
            assert img.tag == 'img'
            assert img.attrs['src'] == 'res://' + theme.resource_path(
                'icons/alert-%s-%s.png' % (name, kind))
            label = title.find('span', 'altx')[0]
            assert ''.join(n.text for n in label.walk()).strip() == name.capitalize()
        check_anchor_texts(ALERTS, [a for o in outs for a in Page(o).anchors])


def img_ctx(avail=600, doc_dir='C:\\문서 폴더\\하위'):
    return render.RenderContext(16, 12, 34, 'light', avail=avail, metrics=METRICS, fonts=FONTS,
                                doc_dir=doc_dir)


def render_img(text, ctx=None, sizes=None):
    ctx = ctx or img_ctx()
    sizes = sizes if sizes is not None else {}
    asked = []

    def size(path):
        asked.append(path)
        return sizes.get(os.path.basename(path))
    doc = blocks.parse(text)
    outs = [render.render_block(b, doc, ctx, fake_measure, image_size=size) for b in doc.blocks]
    return outs, asked


def test_local_image_src_size_and_edit_link():
    outs, asked = render_img('see ![a](<그림 1.png>) and ![b](sub/big.jpg)\n',
                             sizes={'그림 1.png': (120, 80), 'big.jpg': (3000, 1000)})
    assert asked == [os.path.join('C:\\문서 폴더\\하위', '그림 1.png'),
                     os.path.join('C:\\문서 폴더\\하위', 'sub', 'big.jpg')]
    root = Tree(outs[0]).root
    small, big = root.find('img')
    assert small.attrs['src'] == 'file://C:/문서 폴더/하위/그림 1.png'
    assert (small.attrs['width'], small.attrs['height']) == ('120', '80')
    # wider than the available width: scaled down to it, aspect kept
    assert (big.attrs['width'], big.attrs['height']) == ('600', '200')
    # each image sits in its line's edit link
    edit = [a for a in root.find('a') if a.attrs.get('class') == 'e']
    assert [a.attrs['href'] for a in edit if a.find('img')] == ['mdgh:e:0', 'mdgh:e:0']
    assert_within_allow_lists(outs)


def test_image_width_follows_the_containing_block():
    outs, _ = render_img('> - ![q](w.png)\n', sizes={'w.png': (5000, 100)})
    w = int(Tree(outs[0]).root.find('img')[0].attrs['width'])
    assert w == 600 - (M['bar'] + 2 * M['quote_pad']) - M['indent']


def test_images_without_a_readable_local_file_show_alt_text():
    text = ('![gone](missing.png) ![vec](logo.svg) ![abs](C:/x.png) '
            '![web](https://x.test/p.png) [![inl](https://x.test/q.png)](https://x.test/r)\n')
    outs, asked = render_img(text)
    root = Tree(outs[0]).root
    assert not root.find('img')
    assert len(asked) == 1                      # only the relative bitmap is looked up
    links = {a.attrs['href']: ''.join(n.text for n in a.walk()) for a in root.find('a')
             if a.attrs.get('class') != 'e'}
    assert links == {'https://x.test/p.png': 'web', 'https://x.test/r': 'inl'}
    edit_text = ''.join(t for _, t in Page(outs[0]).anchors)
    assert 'gone' in edit_text and 'vec' in edit_text and 'abs' in edit_text
    # an unsaved buffer has no folder for relative paths
    outs, asked = render_img('![a](a.png)\n', ctx=img_ctx(doc_dir=''), sizes={'a.png': (1, 1)})
    assert asked == [] and not Tree(outs[0]).root.find('img')


def test_image_inside_a_link_is_not_wrapped_in_an_edit_link():
    outs, _ = render_img('[![a](a.png)](https://x.test)\n', sizes={'a.png': (10, 10)})
    p = Page(outs[0])
    assert not p.nested_a
    link = [a for a in Tree(outs[0]).root.find('a') if a.attrs['href'] == 'https://x.test'][0]
    assert link.find('img')


def test_images_in_table_cells_and_ordered_items_fit_their_box():
    text = '| ![t](t.png) | b |\n|---|---|\n| c | d |\n\n1. ![o](o.png) after\n'
    outs, _ = render_img(text, ctx=img_ctx(avail=300), sizes={'t.png': (900, 90), 'o.png': (900, 90)})
    assert_within_allow_lists(outs)
    t_img = Tree(outs[0]).root.find('img')[0]
    o_img = Tree(outs[1]).root.find('img')[0]
    assert int(t_img.attrs['width']) <= 300 - 2 * M['cell_px']
    assert int(o_img.attrs['width']) <= 300 - M['indent'] - layout.SAFETY
    # the image is a word of its own: the following text wraps to the next line
    lc = Tree(outs[1]).root.find('span', 'lc')[0]
    assert lc.find('br') and lc.find('a')[0].find('img')


@pytest.mark.parametrize('n,depth,marker', [
    (1, 0, '1.'), (12, 0, '12.'), (1, 1, 'i.'), (4, 1, 'iv.'), (9, 1, 'ix.'), (14, 1, 'xiv.'),
    (1990, 1, 'mcmxc.'), (1, 2, 'a.'), (26, 3, 'z.'), (27, 2, 'aa.'), (0, 1, '0.'), (0, 2, '0.'),
])
def test_list_marker_styles(n, depth, marker):
    assert render.list_marker(n, depth) == marker


def test_nested_ordered_lists_use_roman_then_alpha_markers():
    # a nested list interrupts its item's paragraph only when it starts at 1 (CommonMark)
    text = '1. a\n   1. b\n      1. c\n         1. d\n         2. e\n\n- x\n  1. y\n'
    _, outs = render_all(text)
    marks = [m.children[0].text for m in Tree(outs[0]).root.find('span', 'mk')]
    assert marks == ['1.', 'i.', 'a.', 'a.', 'b.']
    # an ordered list inside a bullet list is nested too (GitHub: ul ol is lower-roman)
    assert [m.children[0].text for m in Tree(outs[1]).root.find('span', 'mk')] == ['i.']


def test_block_pads_centre_content_at_the_maximum_width():
    pl, pr, avail = render.block_pads(1388, 32, 980)
    assert avail == 980 and abs(pl - pr) <= 1 and pl + pr + avail == 1388
    pl, pr, avail = render.block_pads(1389, 30, 1225.0)      # 980 at 20px body text
    assert avail == 1225 and abs(pl - pr) <= 1 and pl + pr + avail == 1389
    # narrower than the maximum: the side padding stays at its minimum
    assert render.block_pads(900, 32, 980) == (32, 32, 836)
    # 0 turns the maximum off
    assert render.block_pads(3000, 32, 0) == (32, 32, 2936)
    assert render.block_pads(40, 32, 980) == (32, 32, 0)


# ---------------------------------------------------------------- front matter


FRONT = ('---\n'
         'title: Hello there\n'
         'tags: [a, b]\n'
         'items:\n'
         '  - one\n'
         '  - two\n'
         'meta:\n'
         '  depth: 2\n'
         '---\n'
         '\n'
         'body\n')


def text_of(node):
    return ''.join(n.text for n in node.walk())


def test_front_matter_is_a_table_of_keys_over_values():
    doc, outs = render_all(FRONT)
    assert doc.blocks[0].kind == 'front_matter'
    root = Tree(outs[0]).root
    rows = root.find('div', 'tr')
    assert len(rows) == 2
    head, vals = ([c for c in r.children if c.tag == 'span'] for r in rows)
    assert all('th' in c.cls for c in head) and not any('th' in c.cls for c in vals)
    assert [text_of(c).strip('\u200b\xa0 ') for c in head] == ['title', 'tags', 'items', 'meta']
    # a value outside the subset keeps its source lines (indentation too) in the code font class
    assert text_of(vals[3].find('span', 'fmr')[0]) == '\xa0\xa0depth: 2'
    # list items are one per line
    assert len(vals[2].find('div', 't')) == 2
    assert_within_allow_lists(outs)


def test_front_matter_edit_links_point_at_each_values_source_line():
    _, ps = pages(FRONT)
    got = sorted((r, t.replace('\xa0', ' ').strip()) for r, t in ps[0].anchors)
    assert got == [(1, 'Hello there'), (1, 'title'), (2, 'a'), (2, 'b'), (2, 'tags'),
                   (3, 'items'), (4, 'one'), (5, 'two'), (6, 'meta'), (7, 'depth: 2')]
    check_anchor_texts(FRONT, ps[0].anchors)


def test_unreadable_front_matter_stays_a_code_block():
    _, outs = render_all('---\n- a\n- b\n---\n')
    root = Tree(outs[0]).root
    assert root.find('div', 'pre') and not root.find('div', 'tr')
    assert [r for r, _ in Page(outs[0]).anchors] == [1, 2]


# ---------------------------------------------------------------- raw HTML subset


def test_inline_html_subset_renders_and_other_tags_stay_escaped_text():
    text = 'a <kbd>Ctrl</kbd>+<kbd>C</kbd> H<sub>2</sub>O x<sup>2</sup> one<br>two <b>bold</b>\n'
    _, outs = render_all(text)
    root = Tree(outs[0]).root
    assert [text_of(k) for k in root.find('code', 'kbd')] == ['Ctrl', 'C']
    assert text_of(root.find('span', 'sub')[0]) == '2'
    assert text_of(root.find('span', 'sup')[0]) == '2'
    assert len(root.find('br')) == 1
    assert not root.find('b') and '<b>bold</b>' in text_of(root)
    assert_within_allow_lists(outs)


@pytest.mark.parametrize('text', [
    'a <kbd>open only\n',
    'a </kbd> close only </sup>\n',
    '<sub><sup>a</sub>b</sup>\n',
    'x <img> <img src=> <img src="p.png" width="wide" height="-3"> </img>\n',
    '<details>\n<summary>never closed\n',
    '</summary><summary><details></details>\n',
    '<details><summary>a<kbd>b</summary>c</details>\n',
    '| <kbd>a | <sup>b</sub> |\n|---|---|\n| <br> | </kbd> |\n',
    '1. <kbd>k</kbd><br><sub>s\n',
])
def test_broken_html_tags_render_balanced_markup(text):
    outs, _ = render_img(text, sizes={'p.png': (40, 20)})
    for out in outs:
        Tree(out)           # asserts every element is closed in order
    assert_within_allow_lists(outs)


def test_html_img_uses_its_width_and_height_attributes_within_the_box():
    text = ('<img src="a.png" width="50" height="30"> <img src="a.png" width="25%"> '
            '<img src="a.png" height="10" alt="x"> <img src="b.png" width="9000">\n')
    outs, _ = render_img(text, ctx=img_ctx(avail=400),
                         sizes={'a.png': (200, 100), 'b.png': (800, 400)})
    sizes = [(int(i.attrs['width']), int(i.attrs['height'])) for i in Tree(outs[0]).root.find('img')]
    assert sizes == [(50, 30), (100, 50), (20, 10), (400, 200)]
    outs, _ = render_img('<img src="gone.png" alt="the alt">\n')
    assert not Tree(outs[0]).root.find('img') and 'the alt' in text_of(Tree(outs[0]).root)


def test_details_summary_is_a_marked_title_and_its_content_renders_as_markdown():
    text = ('<details>\n<summary>More <kbd>K</kbd></summary>\n\nInside **bold**\n\n</details>\n\n'
            'after\n')
    doc, outs = render_all(text)
    # the closing tag draws nothing, so it is not a block
    assert [b.kind for b in doc.blocks] == ['html_block', 'paragraph', 'paragraph']
    head = Tree(outs[0]).root
    title = head.find('div', 'sm')[0]
    assert text_of(title).startswith(render.SUMMARY_MARKER) and title.find('code', 'kbd')
    assert 'dsum' in head.find('div', 'blk')[0].cls
    assert [r for r, _ in Page(outs[0]).anchors] == [1, 1]
    assert Tree(outs[1]).root.find('b')
    assert 'dsum' not in Tree(outs[2]).root.find('div', 'blk')[0].cls


def test_details_without_summary_gets_the_default_title_at_its_row():
    _, outs = render_all('intro\n\n<details>\n\ntext\n\n</details>\n')
    title = Tree(outs[1]).root.find('div', 'sm')[0]
    assert render.DEFAULT_SUMMARY in text_of(title)
    assert [r for r, _ in Page(outs[1]).anchors] == [2]


def test_html_blocks_without_subset_tags_stay_escaped_code():
    _, outs = render_all('<div align="center">\n  <p>x</p>\n</div>\n')
    root = Tree(outs[0]).root
    assert root.find('div', 'pre') and [r for r, _ in Page(outs[0]).anchors] == [0, 1, 2]


def test_html_block_with_subset_tags_flows_with_other_tags_escaped():
    outs, _ = render_img('<p align="center">\n<img src="a.png" width="20">\n</p>\n',
                         sizes={'a.png': (40, 40)})
    root = Tree(outs[0]).root
    assert not root.find('div', 'pre')
    assert [(i.attrs['width'], i.attrs['height']) for i in root.find('img')] == [('20', '20')]
    assert {r for r, _ in Page(outs[0]).anchors} == {0, 1, 2}
    assert '<p align="center">' in text_of(root)


def test_kbd_and_br_in_table_cells_are_measured_boxes_and_breaks():
    _, outs = render_all('| <kbd>A</kbd><kbd>B</kbd> | x<br>y |\n|---|---|\n| c | d |\n')
    first = Tree(outs[0]).root.find('div', 'tr')[0]
    cells = [c for c in first.children if c.tag == 'span']
    assert len(cells[0].find('code', 'kbd')) == 2       # one box per kbd element
    assert len(cells[1].find('div', 't')) == 2          # the break makes a second line


# ---------------------------------------------------------------- remote images


def test_remote_urls_lists_markdown_and_html_images():
    doc = blocks.parse('![a](https://x.test/a.png) <img src="http://x.test/b.gif"> '
                       '![l](local.png) ![a2](https://x.test/a.png)\n\n'
                       '<img src="https://x.test/c.png">\n')
    assert [render.remote_urls(b) for b in doc.blocks] == [
        ('https://x.test/a.png', 'http://x.test/b.gif'), ('https://x.test/c.png',)]


def test_cached_remote_images_render_as_local_files_and_others_stay_links():
    doc = blocks.parse('![a](https://x.test/a.png) ![b](https://x.test/b.svg)\n')
    cache = {'https://x.test/a.png': 'C:\\cache\\0a.png'}
    sizes = {'C:\\cache\\0a.png': (30, 20)}
    out = render.render_block(doc.blocks[0], doc, img_ctx(), fake_measure,
                              image_size=sizes.get, remote=cache.get)
    root = Tree(out).root
    assert [i.attrs['src'] for i in root.find('img')] == ['file://C:/cache/0a.png']
    assert [a.attrs['href'] for a in root.find('a') if a.attrs.get('class') != 'e'] == \
        ['https://x.test/b.svg']
    # without the remote lookup (remote_images off) both stay alt text links
    out = render.render_block(doc.blocks[0], doc, img_ctx(), fake_measure, image_size=sizes.get)
    assert not Tree(out).root.find('img')
