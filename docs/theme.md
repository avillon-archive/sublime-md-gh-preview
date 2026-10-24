# 테마와 글자 크기

## 테마 구성

- 테마는 변수 JSON(`themes/github-light.json`·`github-dark.json`: 색, GitHub 16px 본문 기준 크기·줄 간격)이다. 이 값에서 (a) `phantom_css`(CSS 템플릿 `themes/base.css` + 사용자 CSS), (b) 미리보기 scheme 의 globals, (c) 코드 하이라이트 scheme 의 선택을 만든다.
- 테마 설정은 `github-light`(기본)·`github-dark`·`auto` 다. 에디터 scheme 이 어두워도 기본값은 `github-light` 이고, 밝기를 따르려면 `auto` 를 쓴다.
- **테마 CSS 는 미리보기 color scheme 의 `phantom_css` 에 둔다.** CSS 가 한곳에 모이고, 사용자 CSS 가 같은 cascade 안에서 기본 규칙을 덮을 수 있다. 블록 phantom 에는 마크업과 폭에 따라 달라지는 inline 값만 들어간다([rendering.md](rendering.md) §렌더러).
- CSS 길이는 scheme 을 만들 때 본문 px 로 계산한 px 값으로 쓴다(템플릿 자리표시자 `{px.*}`·`{lh.*}`·`{c.*}`). 그래서 글자 크기가 바뀌면 새 scheme 을 만들고 다시 렌더한다.
- 페이지 배경은 scheme 의 `background` 다. phantom 은 페이지 배경을 칠하지 않으므로 블록 사이의 틈과 도구줄이 같은 색으로 이어진다. 그래서 사용자 CSS 로 페이지 배경을 바꿀 수 없다.

### 줄 간격

minihtml 은 줄 간격을 글꼴의 자연 높이 h 보다 작게 만들지 않고, 그보다 큰 line-height L 을 주면 (h + L) / 2 로 잡는다. GitHub 의 줄 간격 p(본문 1.5, 코드 1.45 × 글자 크기)를 내려면 L = 2p − h 를 넣는다. h 는 같은 글꼴·크기의 측정 panel 에서 `line_height()` 로 얻는다. GitHub 줄 간격이 h 보다 작은 요소(제목 1.25)에는 line-height 를 주지 않는다.

### 사용자 CSS

- `custom_css` 의 파일 목록(리소스 경로 또는 절대 경로)을 기본 CSS 뒤에 이어 `phantom_css` 에 넣는다. minihtml 이 지원하는 속성만 동작하고, `var()` 는 값 전체에만 쓸 수 있다.
- `base.css` 의 `html{}` 변수에는 두 규칙 이상이 참조하는 값만 둔다. 변수 정의는 phantom 마다 다시 처리되어 일반 선언보다 훨씬 비싸다. 규칙 하나만 쓰는 값은 템플릿 자리표시자로 그 규칙에 바로 쓴다. 사용자 입장에서는 그 규칙을 덮는 것이 변수를 바꾸는 것과 같다. 사용자용 예시는 레포 루트 `README.md` 에 있다.
- Sublime Text 는 phantom 마다 `phantom_css` 전체를 다시 처리한다. 그래서 블록당 배치 비용은 CSS 선언 수에 비례하고, 사용자 CSS 를 많이 더하면 진입 시간이 길어진다.

### 글꼴

본문·고정폭 글꼴을 각각 설정 하나(`font_body`·`font_mono`, 단일 글꼴 이름)로 받는다. 측정 panel 의 `font_face` 와 CSS `font-family` 의 첫 항목이 같아야 측정이 맞기 때문이다([layout.md](layout.md)). 설정이 null 이면 플랫폼별 기본값(`controller._PLATFORM_FONTS`)을 쓴다. 한글은 OS 대체 글꼴로 그려진다.

### auto 판정

- 미리보기에 들어갈 때 그 view 의 `view.style()["background"]` 밝기(0.5 미만이면 dark)로 고르고, 결과를 `state.theme` 에 적는다.
- 미리보기 중에는 view 의 style 이 미리보기 scheme 이므로, 숨김 panel(`theme.AUTO_PANEL`)에 그 view 의 syntax 를 `assign_syntax` 하고(진입 전 view 수준 `color_scheme` 이 있었으면 그 값도 panel 에 둔다) panel 의 `style()["background"]` 로 다시 판정한다. syntax 별 `color_scheme` 은 panel 에 바로 반영된다.
- 다시 판정하는 때는 `Preferences.sublime-settings` 가 바뀔 때(`add_on_change`)와 미리보기 view 가 활성화될 때다. `add_on_change` 콜백 안에서는 이미 있는 panel 의 `style()` 이 옛 값을 돌려주므로 `set_timeout(…, 0)` 으로 다음 틱에 판정한다.

## 미리보기 color scheme

- scheme 은 `globals` 만 갖고 scope 규칙은 없다. 남겨 둔 원문 글자가 Markdown syntax 의 scope 색을 받으면 안 되기 때문이다.
- globals: `background` 는 테마 배경색이다. `foreground`, `fold_marker`, `caret`, 선택·하이라이트·안내선 계열 색(`theme._HIDDEN_GLOBALS`)은 모두 배경색이다. `phantom_css` 는 테마 CSS 다.
- fold 마커의 점은 Sublime Text 가 `fold_marker` 색을 어둡게 한 색으로 그린다. 밝은 배경에서는 회색 점이 남고, 어두운 배경에서는 거의 보이지 않는다. 투명색·배경색·foreground 를 바꿔도 점은 그대로다. 점의 자리는 배치 A 에서 문서 맨 끝, 배치 B 에서 도구줄 버튼 오른쪽이다([preview-view.md](preview-view.md)).

### scheme 파일

- 경로는 `Packages/User/<패키지 폴더>/<테마>-<해시>.hidden-color-scheme` 이다. 해시의 입력은 scheme 내용 전체(테마 변수, 사용자 CSS, 글꼴, 본문 px)다. 입력이 바뀌면 새 해시의 파일을 쓴다.
- 같은 이름의 파일을 고쳐 쓰지 않는다. Sublime Text 가 약 1초 뒤 파일을 다시 읽어 그려진 phantom 의 높이가 바뀌는데, 그 시점을 알 수 없어 y 표를 다시 잴 때를 정할 수 없다.
- 새로 쓴 scheme 파일을 곧바로 view 에 지정하면 "Error loading colour scheme" 모달이 뜬다. 새 파일이 리소스로 잡힌 것을 `sublime.find_resources` 로 확인한 뒤 미리보기 view 들에 지정하고 다시 렌더한다.
- 미리 만들기: `plugin_loaded` 와 확대·축소 단계마다 현재 `font_scale` 과 그 앞뒤 한 단계 `font_scale` 의 파일을 미리 만든다. 테마 설정이 `auto` 이면 light·dark 둘 다, 아니면 그 종류만 만든다.
- 정리: view 의 scheme 이 바뀌고 1초 뒤에, 열린 view 가 참조하는 파일, 인덱싱을 기다리는 파일, 미리 만든 파일, 최근에 쓴 파일 `theme.SCHEME_KEEP_RECENT` 개(mtime 순)를 남기고 나머지를 지운다. scheme 을 고르거나 view 에 지정할 때 mtime 을 갱신한다.
- 닫힌 프로젝트 workspace 의 view 는 `sublime.windows()` 순회에 나타나지 않는다. 그 view 의 scheme 파일이 지워진 채 프로젝트를 다시 열면 "Error loading colour scheme" 모달이 뜬다. 최근 파일 보존은 이 위험을 줄일 뿐이고, 오래 닫혀 있던 프로젝트의 scheme 은 밀려날 수 있다.

## 글자 크기와 확대·축소

- 본문 크기는 16px × `font_scale` 이다. 에디터 `font_size` 는 본문 크기 계산에 쓰지 않는다. 나머지 크기는 GitHub 값 × (본문 px / 16) 이다. 도구줄 버튼은 에디터 줄 안에 있으므로 에디터 글자 크기(`font_size` × 4/3)를 따른다.
- 패키지 keymap(대상 view context)과 mousemap(`Ctrl+휠`, mousemap 에는 context 가 없다)이 Sublime Text 기본 확대·축소 바인딩을 `mdgh_preview_zoom` 으로 덮는다. 대상 view 에서는 `font_size` ±1 과 함께 `font_scale` 을 같은 비율로 바꿔 두 설정 파일에 저장하고, 대상이 아닌 view 에서는 Sublime Text 기본 명령을 그대로 실행한다.
- 비율은 매 단계 직전 값이 아니라 기준점 (font_size, font_scale)에서 계산한다(`theme.zoom_scale`). 반올림 오차가 쌓이지 않아 같은 `font_size` 로 돌아오면 정확히 같은 `font_scale` 이 된다. `font_scale` 을 손으로 고쳤거나 확대·축소 밖에서 `font_size` 가 바뀌어 기준점과 맞지 않으면 새 기준점에서 시작한다.
- Sublime Text 는 패키지 설정 변경을 같은 값으로 한 번 더 알리므로, 값이 직전과 같은 알림은 무시한다.
