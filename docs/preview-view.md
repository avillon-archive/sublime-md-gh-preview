# 미리보기 view 구조

미리보기는 같은 view 에서 원문을 fold 로 감추고 그 자리에 블록 phantom 을 그린 상태다. 이 문서는 그 구조와 모드 상태의 저장·복구를 설명한다. 블록 내용을 만드는 과정은 [rendering.md](rendering.md), 다시 그리는 일정은 [updates.md](updates.md) 가 설명한다.

## 표시 구조

### fold 와 도구줄

fold 하나로 원문을 감추고, 줄 1 을 도구줄(전환 버튼이 놓이는 줄)로 쓴다. 배치는 두 가지이고, 렌더할 때마다 고른다.

- **배치 A**: 줄 1 과 버튼이 한 표시 줄에 들어갈 때 쓴다. 이 조건은 편집 모드 버튼이 줄 1 의 유일한 표시 줄에 놓이는 조건과 같다. 줄 2 부터 끝까지 `[line(0).b + 1, size)` 를 접고, 줄 1 은 그대로 남긴다. 미리보기 scheme 의 foreground 가 배경색이므로 남은 줄 1 의 글자는 보이지 않는다. fold 마커는 줄 2 의 표시 줄, 즉 모든 블록 아래(문서 맨 끝)에 그려진다. 도구줄 버튼은 편집 모드 버튼과 같은 자리(줄 1 끝, 오른쪽 끝)에 놓인다. 줄이 하나뿐인 문서에는 접을 범위가 없다.
- **배치 B**: 줄 1 이 길어서 버튼과 한 표시 줄에 들어가지 않을 때 쓴다. `[1, size)` 를 접어 첫 글자만 남기고(이 글자도 보이지 않는다), 줄 1 을 도구줄로 쓴다. fold 마커는 도구줄 버튼 바로 오른쪽에 그려진다. 이 경우에 배치 A 로 줄 1 을 남기면 줄 1 이 여러 표시 줄을 차지해 블록 위에 빈 띠가 생긴다.

제약:

- `[0, size)` 로 접으면 안 된다. fold 시작 point 에 건 phantom 은 block·inline 모두 그려지지 않는다.
- 블록마다 따로 접으면 안 된다. fold 마다 "…" 마커가 블록 사이에 남는다.

### phantom anchor 와 추가 순서

- anchor 는 배치 A 에서 `Region(line(0).b)`(줄 1 끝), 배치 B 에서 `Region(0)` 이다. 도구줄 버튼(`LAYOUT_INLINE`)을 먼저 추가하고, 이어서 블록 phantom(`LAYOUT_BLOCK`)을 같은 anchor 에 문서 순서대로 `view.add_phantom` 으로 추가한다. 같은 point 의 block phantom 은 줄 1 아래에 추가한 순서대로 쌓인다.
- 버튼은 반드시 블록보다 먼저, 블록과 같은 point 에 추가한다. 블록 뒤에 추가한 inline phantom 은 그려지지 않고, 같은 줄의 다른 point 에 둔 inline phantom 은 블록 영역의 세로 가운데에 그려진다. 그래서 버튼을 다시 놓아야 하면(폭·글자 크기·테마 변경) 블록도 모두 지우고 버튼 → 블록 순서로 다시 추가한다.
- anchor 를 `Region(size)` 에 두면 안 된다. 문서 끝에 글자가 붙으면 anchor 가 옛 끝에 남는데, fold 를 새 끝까지 다시 잡는 순간 모든 블록이 fold 안에 들어가 숨겨진다. 배치 B 의 `Region(0)` 은 어디에 글자를 넣어도 (0, 0) 에 남는다. 배치 A 의 줄 1 끝 anchor 는 줄 1 밖의 편집이나 줄 1 안의 글자 삽입에는 줄 1 에 남고, 줄 1 을 둘로 나누는 개행이 들어오면 다음 줄로 밀린다([updates.md](updates.md) §편집).
- phantom 의 순서는 추가 순서로 정해지므로, 중간 블록 하나를 바꾸려면 그 블록부터 끝까지 지우고 다시 추가한다. 블록 id 는 `add_phantom` 의 반환값이고, 지울 때는 `erase_phantom_by_id` 를 쓴다. `PhantomSet.update` 로 여러 개를 한 번에 넣으면 블록마다 top y 를 잴 수 없으므로 쓰지 않는다.
- 블록 여러 개를 phantom 하나로 묶지 않는다. 스크롤 동기화·더블클릭·위치 복원이 블록 정밀도를 가지려면 y 표가 블록 단위여야 한다. 그 대가로 phantom 마다 드는 고정 배치 비용이 진입 시간의 하한을 정하고, 진입 시간은 블록 수에 비례한다.

### y 표

- 블록을 추가하기 직전에 읽은 `layout_extent()[1]` 이 그 블록의 top y 다. 이 y 표가 블록과 화면 위치를 잇는 유일한 출처다.
- extent 에서 그려진 높이를 얻는 곳은 모두 "extent − fold 줄 − 보류 spacer" 를 쓴다. 배치 A 에서 fold 가 있으면 맨 아래 fold 줄 높이(에디터 줄 높이 하나)가 extent 에 들어 있고, 보류 spacer 가 있으면 그 높이도 들어 있다.
- block phantom 하나는 내용 높이에 4px(내용 위 3px)를 더한 높이를 차지한다.

### 보류 spacer

다시 그리는 동안 viewport 를 붙잡아 둘 빈 block phantom(`controller.SPACER_KEY`, 높이 `controller.HOLD_SPACER_PX`)이다. 쓰는 시점은 [updates.md](updates.md) §다시 그리는 동안의 화면 이 설명한다.

- `Region(size)` 에 둔다. 블록 anchor 에 나중에 추가한 블록은 spacer 위로 들어간다.
- 문서 끝에 글자가 붙으면 spacer 의 anchor 가 옛 끝에 남아 fold 안에 들어가므로, 보류 중에 버퍼가 바뀌면 spacer 를 새 끝에 다시 놓는다.
- 줄이 하나뿐인 문서는 끝이 블록 anchor 와 같으므로 spacer 를 두지 않는다.

### 미리보기 중의 view 설정

- view 의 `color_scheme` 을 미리보기 전용 hidden scheme([theme.md](theme.md) §미리보기 color scheme)으로 바꾸고, `controller.PREVIEW_VALUES` 의 값(gutter·줄 번호·들여쓰기 안내선 끄기, `word_wrap` 켜기, `scroll_past_end` 끄기, `is_widget` 등)을 둔다.
- 미리보기 view 의 `font_size` 와 `line_padding_*` 는 바꾸지 않는다. 마우스 휠 스크롤은 줄 단위(1노치 = 3줄)라서 줄 높이를 줄이면 휠이 느려지고, `scroll_speed` 로는 이를 보정할 수 없다.
- selection 을 비워 캐럿을 없애고, 상태바에 `Preview` 를 표시한다.
- 블록 사이 간격과 여백은 전부 phantom CSS 가 정한다.
- 빈 버퍼(size 0)는 fold 없이 흐린 `Empty document` 블록 하나를 그린다.

## 모드 상태와 복구

### 진입 전 상태 저장

- view 설정 `mdgh_preview.state` 가 미리보기 표식과 복구 정보를 갖는다. 진입 전의 **view 수준** 설정값(`saved`), `auto` 테마 판정 결과(`theme`), 진입 직전의 viewport 위치와 `change_count()`, 미리보기 중 재로드 여부가 들어간다. view 설정은 세션에 함께 저장된다.
- view 수준 값의 판별: 미리보기가 바꾸는 키마다 같은 콜백 안에서 값을 읽고(v1), erase 한 뒤 다시 읽는다(v2). v1 ≠ v2 이면 view 수준 값 v1 이 있었으므로 `saved` 에 적고, 같으면 상속값이므로 적지 않는다. erase 직후 읽은 값은 즉시 상속값이 된다. `Settings.has`·`in`·`to_dict()` 는 상속값도 참으로 보므로 판별에 쓰지 않는다.
- selection 과 사용자 fold 는 진입할 때 hidden region(`HIDDEN | PERSISTENT`)으로 저장한다. region 은 clone view 의 편집을 따라 위치가 옮겨진다.

### 복귀

- 미리보기 키를 모두 erase 한 뒤 `saved` 에 있는 키만 다시 설정한다. 그래서 미리보기 중에 전역·syntax 설정이 바뀌었으면 복귀한 뒤 새 값을 따른다.
- 저장한 selection 과 사용자 fold 를 되돌린다. 재로드는 region 을 옮기지 않아 옛 좌표가 그대로 남으므로, 미리보기 중에 재로드가 있었으면 저장한 region 을 버리고 캐럿만 동기화한 줄의 첫머리에 둔다(사용자 fold 는 복원하지 않는다).
- 복귀 위치는 [interaction.md](interaction.md) §스크롤 동기화 가 정한다.

### 플러그인 재로드와 종료

- 모듈 메모리 상태(블록 표, phantom id, y 표, 캐시)는 플러그인 재로드나 Sublime Text 재시작 때 사라진다. `plugin_loaded` 는 표식이 있는 view 를 다시 그린다. 보이는 view(창마다 그룹별 활성 view)는 바로 그리고, 나머지는 처음 활성화될 때 그린다.
- `plugin_unloaded` 는 열린 미리보기를 모두 편집 상태로 되돌린다. 패키지를 끄거나 업그레이드한 뒤 접힌 view 가 남지 않게 하기 위해서다. 비정상 종료로 `plugin_unloaded` 가 불리지 않으면 view 가 접힌 채 세션에 남고, 다음 `plugin_loaded` 가 표식을 보고 다시 그린다.
- Sublime Text 를 재시작한 직후 플러그인이 로드되기 전까지, 미리보기 탭은 원문이 배경색 글자로 그려진 빈 화면이다(세션이 미리보기 중의 view 설정을 저장하기 때문이다). 종료 이벤트에서 설정을 되돌리는 방식은 일부 종료 경로에서만 세션 저장보다 먼저 실행되므로 쓰지 않는다.
- `on_pre_close` 는 모드 기억을 쓰고, view 의 메모리 상태를 지우고, 그 view 가 버퍼의 마지막 미리보기 view 이면 TextChangeListener 를 떼어 낸다. 편집 상태로 되돌리지는 않는다. `is_widget` 이므로 BufferScroll 이 미리보기 상태를 저장하지 않고, 닫힌 view 는 세션에 남지 않기 때문이다.
- clone view 는 서로 독립이다. 미리보기 상태, 버튼, fold, selection 이 모두 view 단위다.

## 모드 기억

- 저장소는 `sublime.cache_path()/<패키지 폴더>/modes.json` 이고, 파일 경로를 {미리보기 화면 맨 위의 원문 줄, 시각} 에 대응시킨다.
- 마지막 모드가 미리보기인 파일만 적고, 편집으로 바꾸면 그 항목을 지운다. 항목 수가 상한(`modestore.ModeStore` 의 `limit`)을 넘으면 오래된 것부터 지운다. 파일 경로가 없는 버퍼는 기억하지 않는다. `remember_mode` 가 false 이면 읽지도 쓰지도 않는다.
- 기록이 없는 파일은 편집 모드로 연다. 기록이 미리보기인 파일은 기억한 원문 줄의 블록이 화면 맨 위에 오게 미리보기로 연다.
- 기준 줄(화면 맨 위 원문 줄)을 구하는 방법: 그리기가 끝났으면 화면 맨 위 y 를 블록 표로 역산한다. 그리는 중이면 아직 적용하지 않은 보류 위치가 가리키는 원문 줄(블록 시작 줄 + 블록 안 비례 위치)을 쓰고, 보류 위치가 없으면 그려진 블록 표로 역산한다. 그리는 중의 viewport 는 Sublime Text 가 그려진 내용 끝에 맞춰 잘라 낸 값이라 사용자가 보던 위치가 아니므로 보류 위치를 우선한다. 미리보기 → 편집 전환도 같은 기준 줄을 쓴다.
