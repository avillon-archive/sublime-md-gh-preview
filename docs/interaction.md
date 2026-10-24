# 전환과 입력

## 전환 수단

| 수단 | 구현 |
|---|---|
| `Ctrl+Shift+V` | `Default.sublime-keymap` → `mdgh_preview_toggle`, context `mdgh_preview.applicable`(`on_query_context`). 대상이 아닌 view 에서는 Sublime Text 기본 `paste_and_indent` 가 그대로 실행된다 |
| 도구줄 버튼 | §도구줄 버튼 |
| 탭 우클릭 메뉴 | `Tab Context.sublime-menu`. 인자 `group`·`index` 로 대상 view 를 찾는다 |
| 편집 영역 우클릭 메뉴 | `Context.sublime-menu` |
| 명령 팔레트 | `Default.sublime-commands`(`Markdown GitHub Preview: Toggle`). 설정 열기는 `Main.sublime-menu`(Preferences > Package Settings) |
| 본문 더블클릭 | §더블클릭 |

- 탭·편집 영역 메뉴 항목의 이름은 명령의 `description()` 이 현재 모드에 맞춰 `Preview` / `Edit Source` 로 바꾼다.
- 대상 판정은 확장자(`file_extensions`)와 syntax scope(`syntax_selector`) 중 하나라도 맞으면 참이다. 기본 selector `text.html.markdown` 은 PlainNotes 의 `.note`(scope `text.html.markdown.note`)도 포함한다.
- 탭에 붙일 수 있는 UI 는 우클릭 메뉴뿐이다.

## 도구줄 버튼

- 버튼은 `LAYOUT_INLINE` phantom 이고, 왼쪽 padding 으로 텍스트 영역 오른쪽 끝에 붙인다. padding = 텍스트 영역 폭 − 버튼 앞 x(`text_to_layout`) − 버튼 폭 − 여백이다. 텍스트 영역 폭은 `viewport_extent()[0]` 이다(`wrap_width`·`draw_centered` 가 있으면 그 폭이다. `layout.text_area_width`). 계산이 넘치면 버튼이 다음 줄로 밀리므로 여백(`layout.BUTTON_MARGIN`)을 넉넉히 둔다.
- 버튼 앞 x 는 버튼 phantom 을 지운 상태에서 잰다. 버튼 phantom 이 `line(0).b` 에 있으면 그 점의 `text_to_layout` 이 버튼 뒤 x(버튼 폭만큼 큰 값)를 돌려주는 상태가 있기 때문이다(새 창에서 연 view, 미리보기 진입 직후). 그래서 버튼을 다시 놓을지는 그 x 가 아니라 줄 1 의 끝 point, 마지막 글자, 그 글자의 `text_to_layout`, 글꼴, 폭으로 판정하고(마지막 글자의 위치는 버튼의 영향을 받지 않는다), 다시 놓을 때는 버튼을 지운 같은 콜백에서 x 를 잰다. 미리보기 증분 갱신에서 "버튼이 그대로인가" 판정도 다시 잰 padding 이 아니라 버튼 html 의 입력(배치, anchor, 배치 A 이면 줄 1 텍스트·배치 B 이면 첫 글자, 에디터 글꼴, 버튼 모드)을 비교한다.
- 편집 모드 버튼은 phantom 안에 자기 `<style>` 을 갖는다. 편집 모드에서는 view 가 사용자 scheme 으로 그려지므로 미리보기 scheme 의 `phantom_css` 가 적용되지 않는다.

### 편집 모드

- 위치는 줄 1 끝(`Region(line(0).b)`)이다. 줄 1 이 한 표시 줄이고 버튼이 들어갈 자리가 있으면 그 줄 오른쪽 끝에 놓인다. 줄 1 이 줄바꿈되면 마지막 표시 줄 오른쪽 끝에 놓이고, 그 줄에 자리가 없으면 다음 표시 줄 오른쪽 끝에 놓인다. 이 경우에만 본문이 한 줄 내려간다. 줄 1 이 길어도 버튼을 숨기지 않는다.
- 줄 1 끝의 캐럿은 버튼 앞(텍스트 끝)에 그려지므로 캐럿과 버튼이 겹치지 않는다.
- 줄 1 끝에 글자를 넣으면 phantom 이 옛 point 에 남아 새 글자가 버튼 뒤에 붙는다. 그래서 `on_modified`(동기 호출, `applies_to_primary_view_only` 가 False 인 ViewEventListener — clone view 마다 버튼이 있다)에서 줄 1 의 끝 point, 마지막 글자, 그 글자의 위치가 바뀌었으면 같은 콜백 안에서 버튼을 새 끝에 다시 놓고 padding 을 다시 계산한다.

### 미리보기 모드

- 배치 A 에서는 편집 모드와 같은 자리(줄 1 끝)다. 두 모드의 버튼을 같은 폭으로 그려(짧은 라벨 쪽에 padding 을 더한다) 전환해도 버튼이 같은 자리에 머물게 한다. 다만 두 모드의 padding 은 각자의 `viewport_extent` 폭으로 계산하는데, 편집 모드의 gutter 가 늘린 텍스트 시작 x 가 두 모드의 `viewport_extent` 폭 차이보다 커서, 줄 1 이 짧은 문서에서는 두 버튼의 화면 x 가 몇 px 다르다.
- 배치 B 에서는 point 0 에서 오른쪽 끝으로 붙이되, 버튼 오른쪽에 첫 글자 폭과 fold 마커 폭을 남긴다.
- 미리보기에 진입할 때 목표가 첫 블록이면 viewport y 를 0 으로 둔다. 첫 블록의 y 로 스크롤하면 도구줄이 화면 위로 밀려 버튼이 보이지 않는다.

### 그리는 때와 모양

- 버튼을 그리는 때는 대상 view 가 열리거나 활성화될 때(`on_load`·`on_activated`·`plugin_loaded`), 대상 판정이 바뀔 때(설정 변경, 활성화·폴링 때 확인하는 syntax 변경), 모드가 바뀔 때, 폴링이 폭·글자 크기 변화를 감지할 때다. 모드를 전환할 때만 그리면 새로 연 파일에 버튼이 없다.
- 모양은 아이콘과 라벨(`Preview` / `Edit`), 흐린 글자색이고, `title` 툴팁은 `Preview (Ctrl+Shift+V)` / `Edit (Ctrl+Shift+V)` 다. 설정 `toggle_button` 이 `icon+text`·`text`·`none` 중에서 모양을 고른다. 고정 UI API 가 없으므로 버튼은 문서와 함께 스크롤된다.
- annotation 은 쓰지 않는다. 마우스를 올리면 상자가 커져 아래 줄을 민다. gutter 아이콘은 클릭이 플러그인에 전달되지 않는다.

## 미리보기 입력 처리

미리보기 view 는 selection 이 항상 비어 있다는 불변식과 명령 가로채기로 편집을 막는다. 명령 분류는 `input.py` 의 상수가 정의한다.

### 마우스

- phantom 위 클릭은 링크가 아니면 플러그인에 전달되지 않는다. 링크 클릭은 `on_navigate` 로 온다.
- 도구줄(줄 1) 클릭은 `drag_select` 로 온다. 그대로 두면 보이지 않는 캐럿과 선택이 생기고, 도구줄을 연달아 누르면 단어·줄 단위 선택을 거쳐 버퍼 전체가 선택되기도 한다. fold 마커를 눌러도 fold 는 풀리지 않는다. 도구줄 위의 마우스 커서는 I-빔이다.

### 텍스트 명령(`on_text_command`)

- `input.BLOCKED_TEXT_COMMANDS`(`drag_select`, `select_all`, undo·redo 계열, fold 계열)는 무효 명령으로 바꾼다.
- `input.HINT_TEXT_COMMANDS`(문자 입력, 붙여넣기, 삭제, 들여쓰기 등)도 무효 명령으로 바꾸고, 상태바에 `Preview — Ctrl+Shift+V to edit` 를 띄운다.
- `input.EDIT_TEXT_COMMANDS`(`find_next`·`find_under` 계열)는 편집 모드로 바꾼 뒤 실행한다. 접힌 텍스트에서 찾기 결과가 나오면 Sublime Text 가 fold 를 풀어 화면이 깨지기 때문이다.
- `move`·`move_to`(PageUp/Down, Home/End, Ctrl+Home/End)는 픽셀 스크롤로 바꾼다(`input.scroll_target`). Page 는 뷰포트 높이 − 줄 높이만큼, Home/End 는 맨 위·맨 아래로 이동한다.
- 화살표 위/아래는 keymap(context `mdgh_preview.preview`)으로 받아 에디터 줄 높이만큼 픽셀 스크롤한다. selection 이 빈 view 에서는 Sublime Text 가 줄 단위 `move` 를 보내지 않아 `on_text_command` 로 받을 수 없다. `Space`/`Shift+Space` 도 같은 context 의 keymap 으로 페이지 스크롤한다.
- 빈 selection 불변식: `on_selection_modified` 에서 미리보기 view 의 selection 이 비어 있지 않으면 바로 비운다. 가로채지 못한 명령에 대비한 장치다.

### 창 명령과 오버레이

- `on_window_command` 에서 `show_panel` 의 `panel` 이 `find`·`replace`·`incremental_find` 이면 편집 모드로 바꾼 뒤 원래 명령을 실행한다.
- `show_overlay` 의 `overlay` 가 `goto` 이고 `text` 가 `:`·`#` 로 시작하면 편집 모드로 바꾼 뒤 실행하고, `@` 로 시작하면 헤딩 quick panel(§Goto Symbol)로 대신한다.
- API 로 연 `show_overlay`(예: 다른 명령이 `text` 를 넣어 연 goto)는 `on_window_command` 에 오지 않는다. 그래서 goto 입력 위젯이 활성화될 때(`view.element() == 'goto_anything:input'`)도 같은 판정을 한다. 입력이 `:`·`#` 이면 오버레이를 닫고 편집 모드로 바꾼 뒤 같은 text 로 다시 열고, `@` 이면 오버레이를 닫고 헤딩 quick panel 을 연다. 이미 열린 오버레이에서 다른 글자 뒤에 `@` 를 치는 경우는 가로채지 않는다.
- 그 밖의 패널·오버레이(Goto Anything, 명령 팔레트, 콘솔, 빌드 결과 등)는 그대로 통과시킨다.

### Goto Symbol

- 미리보기 중의 Goto Symbol 은 헤딩 목록 quick panel 이다. 항목을 highlight 하면 그 블록으로 스크롤하고, 고르면 그 위치에 머물며, 취소하면 원래 위치로 돌아간다.
- quick panel 을 열 때 Sublime Text 가 `on_highlight` 를 동기로 부르므로(0번 항목에 두 번, 그다음 선택 항목에 한 번) 여는 동안의 highlight 는 무시한다.
- goto 오버레이 경로에서는 훅이 돌기 전에 오버레이가 view 를 y 0 으로 옮겨 둔다. 그래서 오버레이 입력이 열릴 때의 y 를 기억했다가 되돌린 뒤 panel 을 연다.
- 다시 그리는 중의 보류 상태([updates.md](updates.md))에서는 보류 위치로 첫 선택 항목을 정하고, 취소하면 보류를 이어 간다.

## 더블클릭

- 같은 `mdgh:e:` href 의 `on_navigate` 가 `controller.CLICK_S` 안에 두 번 오면 그 줄로 편집 모드가 된다(`input.ClickJudge`). 단일 클릭은 모드를 바꾸지 않는다.
- 실제 링크는 첫 `on_navigate` 에서 바로 연다. 같은 간격 안에 같은 href 가 다시 오면 무시한다. 더블클릭으로 두 번 열지 않게 하기 위해서다.

## 스크롤 동기화

- 블록 안의 위치는 비례로 옮긴다. 원문 줄 l(블록 k 의 시작 줄 s_k, 줄 수 n_k)과 미리보기 y 는 y = y_k + (l − s_k) / n_k × h_k 로 대응한다(h_k = 다음 블록 y − y_k). 계산은 `navigation` 모듈이 맡는다.
- **편집 → 미리보기**: 기준 줄은 주 캐럿 줄이 화면 안에 있으면 그 줄이고, 아니면 화면 맨 위 줄이다. 기준 줄의 미리보기 y 가 편집 모드에서 그 줄이 있던 화면 높이에 오게 스크롤한다. 기준이 블록 0 이고 편집 화면이 맨 위였으면 y 를 0 으로 둔다(도구줄이 보이게).
- **미리보기 → 편집**(버튼·단축키·메뉴): 진입 뒤 스크롤도 버퍼 변경도 없었으면 진입 직전의 viewport 와 selection 을 그대로 복원한다. 그렇지 않으면 화면 맨 위 y 를 역산한 원문 줄([preview-view.md](preview-view.md) §모드 기억 의 기준 줄)을 맨 위에 두고, 저장된 selection 이 그 화면 안에 있으면 복원하고, 아니면 그 줄 첫머리에 캐럿을 둔다.
- **더블클릭**: 그 원문 줄이 클릭한 블록 안의 비례 위치와 같은 화면 높이에 오게 하고, 그 줄 첫머리에 캐럿을 둔다.
- **앵커**(`#slug`): 해당 블록의 y 로 애니메이션 스크롤한다.

## 링크

- `http(s)`·`mailto` 는 기본 브라우저(`webbrowser.open`)로 연다.
- `#slug` 는 같은 문서의 해당 블록으로 스크롤한다. href 는 percent-decoding 한 뒤 비교한다.
- 각주 href 는 `#fn-<n>`(각주 n 의 블록)과 `#fnref-<n>`(각주 n 을 처음 참조한 블록)이다.
- 상대 경로 파일(뒤에 `#slug` 를 붙일 수 있다)은 문서 폴더를 기준으로 풀어 Sublime Text 에서 연다. 대상이 미리보기 대상 파일이면 미리보기 모드로 열고, 앵커가 있으면 그 블록으로 스크롤한다. 그 밖의 파일은 그냥 연다. 없는 파일이면 상태바에 알린다.
- 절대 경로, 드라이브 경로, UNC 경로(`\\host\…`)는 열지 않는다. UNC 경로는 파일 존재를 확인하기만 해도 SMB 인증 요청이 나간다. 로컬 이미지 경로도 같은 제약을 따른다.
