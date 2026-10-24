# 미리보기 렌더 확인용 예제 문서 — 첫 줄이 충분히 길어서 화면 폭을 넘으면 annotation 버튼과 어떻게 겹치는지 확인하기 위한 제목입니다

## 상태

**굵은 글씨**와 `inline` 코드, *기울임*이 섞인 문단이다. 상대 경로 링크는 [다른 문서](./other.md)를 가리킨다. ~~취소된 문장~~ 과 일반 문장. English text mixed in for font fallback checks.

> 인용문입니다. GitHub는 왼쪽에 4px 회색 막대를 그립니다.

> [!NOTE]
> GitHub alert 표기입니다. 제목 줄과 색 막대가 보여야 합니다.

### 목록

- 첫째 항목 with `inline code`
- 둘째 항목
  - 중첩 항목 A
  - 중첩 항목 B
- [ ] 할 일 체크박스
- [x] 완료된 체크박스

1. 순서 목록 하나
2. 순서 목록 둘

| 항목 | 정렬 / 표시 | 수치 |
|------|:------:|---:|
| 왼쪽 정렬 셀 — 짧은 설명 | `left` / `code` | 1 |
| 가운데 정렬 확인 | `center` / `code` | 22 |
| 굵은 글씨 셀 | **bold** | 333 |
| Mixed English cell Wide | x | 4444 |

```python
def render(view, blocks):
    # 주석입니다
    for i, b in enumerate(blocks):
        print(f"{i}: {b!r}", 42, None)
    return True
```

```json
{"key": "value", "n": 1.5, "ok": true}
```

---

마지막 문단. 줄바꿈이 있는
소프트 브레이크 문단입니다. [앵커 링크](#목록)

Strike test: ~~deleted English words~~ and ~~삭제된 한글~~ end.

3. 세 번째 순서 항목은 충분히 길어서 화면 폭을 넘어 다음 줄로 넘어가야 합니다. 넘어간 줄이 번호 아래가 아니라 본문 시작 위치에 맞춰 정렬되는지(hanging indent) 확인합니다.
4. 짧은 항목

| 설명 | 값 |
|------|------|
| 한 셀에 긴 문장이 들어가 열 폭을 넘으면 여러 줄로 줄바꿈되고, 이웃한 셀은 그 높이에 맞춰 늘어나며, 줄 사이 간격은 다른 셀과 같아야 한다 | `long` / `wrap` |
| 두 번째 줄도 조금 긴 설명으로 셀 안 줄바꿈을 한 번 더 확인한다 | `short` / `cell` |

### 인라인 코드

인라인 코드가 줄마다 여러 개 들어가는 긴 문단입니다. `render_block` 은 `doc.blocks[k]` 를 받아 `<div class="blk">` 를 만들고, `line_height_css` 가 정한 값은 `p, li, .oi, .t` 에 들어갑니다. 배경 상자가 윗줄·아랫줄 글자를 덮지 않고 줄 사이에 틈이 남는지 봅니다. `theme.build_css` 와 `scaled_lengths` 와 `code_py` 와 `code_px` 가 이어지는 줄도 `font-size: 85%` · `padding: .2em .4em` · `border-radius: 6px` 처럼 같은 간격이어야 합니다. 코드가 든 줄과 없는 줄의 간격이 같은지도 함께 봅니다.

`only_code_here`

코드가 첫 줄에만 있는 문단 `first_line_code` 입니다. 이 문단은 충분히 길어서 두 번째 줄과 세 번째 줄로 넘어가는데, 둘째 줄에는 코드가 없고 셋째 줄 근처에 `third_line_code` 가 다시 나옵니다. 코드가 없는 줄의 간격이 코드가 든 줄과 같아야 합니다. 그 뒤로도 글이 조금 더 이어져 마지막 줄을 채웁니다.

- 목록 항목 안에서 `inline code` 가 줄바꿈되는 경우도 봅니다. 항목이 길어 다음 줄로 넘어가고 거기에도 `second_code` 와 `third_code` 가 있습니다.
- 키보드 표기 <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>V</kbd> 와 `code` 가 한 줄에 함께 있습니다.

| 셀 | 코드가 든 셀 |
|---|---|
| 코드 없는 셀 | `cell_code` 와 `another_code` |
| 여러 줄로 넘어가는 셀에 코드가 섞여 있습니다 | `a` `b` `c` 가 줄마다 이어지는 긴 셀 내용으로 줄바꿈되는지 봅니다 `d` `e` |
