# Markdown GitHub Preview

Sublime Text 4 의 한 탭 안에서 Markdown 원문 편집 모드와 GitHub 스타일 미리보기 모드를 전환하는 패키지다. 미리보기는 Sublime Text 에 내장된 minihtml 로 같은 view 안에 그리므로, 외부 브라우저나 별도 창을 열지 않고 명령 팔레트·Goto Anything·단축키도 그대로 쓸 수 있다.

## 요구 환경

- Sublime Text build 4213 이상이 필요하다. Python 3.14 플러그인 호스트에서 동작하며, Python 3.8 호스트는 지원하지 않는다(동봉한 markdown-it-py 4.x 가 Python 3.10 이상을 요구한다).
- Windows 11(96 DPI)에서 개발하고 검증했다. 다른 OS 에서는 로컬 이미지의 `file://` 경로 형식, 기본 글꼴, 굵은 글꼴 이름(`<글꼴> Bold`)을 확인하지 않았다.
- Markdown 파서(markdown-it-py·mdurl·mdit-py-plugins)는 `lib/` 에 동봉되어 있으므로 따로 설치할 것이 없다.

## 설치

Package Control 기본 채널에는 등록되어 있지 않으므로, 이 레포를 Package Control 에 저장소로 추가해 설치한다.

1. 명령 팔레트에서 `Package Control: Add Repository` 를 실행하고 `https://github.com/avillon-archive/sublime-md-gh-preview` 를 입력한다.
2. `Package Control: Install Package` 를 실행하고 `sublime-md-gh-preview` 를 고른다.

설치된 패키지는 Package Control 이 다른 패키지와 함께 업데이트한다. 패키지 이름은 레포 이름 `sublime-md-gh-preview` 이고, 설정 파일 이름은 `Markdown GitHub Preview.sublime-settings` 다.

## 사용법

### 대상 파일

다음 중 하나에 해당하는 파일에서 미리보기를 쓸 수 있다. 대상이 아닌 파일에는 버튼과 메뉴 항목이 보이지 않는다.

- 확장자가 `file_extensions` 에 있다. 기본값은 `md`·`markdown`·`mdown`·`mkd`·`mkdn` 이다.
- 파일에 지정된 syntax 가 `syntax_selector` 에 맞는다. 기본값 `text.html.markdown` 은 Markdown syntax 가 쓰는 scope 다.

두 조건은 따로 판정한다. 그래서 다른 확장자의 파일을 Markdown syntax 로 열도록 설정해 두었으면(예: `.note` 파일) `file_extensions` 에 없어도 그 파일에 버튼이 보인다. 확장자로만 고르려면 `syntax_selector` 를 `""` 로 둔다.

### 모드 전환

대상 파일에서 다음 수단으로 전환한다.

- `Ctrl+Shift+V`. 대상이 아닌 파일에서는 Sublime Text 기본 동작(`paste_and_indent`)이 그대로 실행된다.
- 편집 영역 오른쪽 위의 `Preview` / `Edit` 버튼. 두 모드 모두에서 항상 보이며 문서와 함께 스크롤된다.
- 탭 우클릭 메뉴와 편집 영역 우클릭 메뉴의 `Preview` / `Edit Source`.
- 명령 팔레트의 `Markdown GitHub Preview: Toggle`.
- 미리보기 본문을 더블클릭하면 그 원문 줄에서 편집 모드가 된다.

모드를 바꿔도 버퍼 내용·저장 상태·undo 기록은 바뀌지 않는다. 편집 모드에서 보던 위치와 미리보기에서 보던 위치는 서로 맞춰진다. 파일마다 마지막 모드와 위치를 기억하므로, 미리보기로 닫은 파일은 다음에 열 때 미리보기로, 보던 위치에서 열린다.

### 미리보기 조작

- 마우스 휠, 화살표 위/아래, `PageUp`/`PageDown`, `Home`/`End`, `Space`/`Shift+Space` 로 스크롤한다.
- 링크를 클릭하면 웹 주소는 기본 브라우저로 열린다. `#제목` 앵커와 각주는 같은 문서 안으로 이동하고, 상대 경로 파일은 Sublime Text 에서 열린다(대상 파일이면 미리보기로 열린다).
- `Ctrl+R`(Goto Symbol)은 제목 목록을 띄운다. 항목을 고르는 동안 그 제목으로 스크롤되고, `Esc` 를 누르면 원래 위치로 돌아간다.
- 찾기(`Ctrl+F`·`Ctrl+H`·`F3` 등)와 줄 이동(`Ctrl+G`)은 편집 모드로 바꾼 뒤 원문에서 실행된다. 미리보기 안에서는 텍스트를 선택하거나 찾을 수 없다.
- 미리보기 중에는 문자 입력·붙여넣기·undo 가 버퍼를 바꾸지 않는다. 같은 파일을 clone 으로 나란히 열면 한쪽에서 편집한 내용이 다른 쪽 미리보기에 바로 반영된다.
- 다른 프로그램(에이전트 등)이 파일을 바꾸면 미리보기가 다시 그려지고 보던 위치가 유지된다.

## 설정

`Preferences > Package Settings > Markdown GitHub Preview > Settings` 에서 연다. 키의 목록과 기본값은 `Markdown GitHub Preview.sublime-settings` 의 주석이 설명한다. 자주 바꾸는 예는 다음과 같다.

```jsonc
{
	// .txt 파일도 미리보기 대상으로 삼는다. 배열 전체가 기본값을 대신하므로 기본 확장자도 함께 적는다.
	"file_extensions": ["md", "markdown", "mdown", "mkd", "mkdn", "txt"],

	// syntax 로는 고르지 않고 file_extensions 의 확장자만 대상으로 삼는다.
	"syntax_selector": "",

	// 에디터 color scheme 의 밝기를 따라 light·dark 를 고른다.
	"theme": "auto",

	// 미리보기 본문 글자를 GitHub 보다 10% 크게 그린다.
	"font_scale": 1.1,

	// 원격 이미지를 내려받아 표시한다(기본값 false 면 네트워크를 쓰지 않는다).
	"remote_images": true
}
```

- 본문 글자 크기는 GitHub 과 같은 16px 에 `font_scale` 을 곱한 값이고, 나머지 크기와 간격은 GitHub 의 비율을 따른다. 에디터 `font_size` 는 미리보기 크기에 영향을 주지 않는다.
- Markdown 파일에서 에디터 확대·축소(`Ctrl+=`, `Ctrl+-`, `Ctrl+휠`)를 쓰면 편집·미리보기 모드 모두에서 에디터 `font_size` 가 1 바뀌고, `font_scale` 도 같은 비율로 바뀐다. 두 값은 설정 파일에 저장되므로 다시 시작해도 유지된다.
- 글꼴은 `font_body`·`font_mono` 에 글꼴 이름 하나씩만 적는다. 글자 폭을 그 글꼴로 측정해 표와 목록을 배치하므로 대체 글꼴 목록은 받지 않는다. 한글은 OS 대체 글꼴로 그려진다.

### 사용자 CSS

`custom_css` 에 CSS 파일 목록(리소스 경로 `Packages/...` 또는 절대 경로)을 적으면 테마 CSS 뒤에 이어 붙으므로, 같은 선택자로 규칙을 다시 쓰면 기본값을 덮는다. 여러 규칙이 함께 쓰는 값(본문 글자색 `--mdgh-fg`, 흐린 글자색 `--mdgh-muted`, 구분선 `--mdgh-rule`, 표 가로선 `--mdgh-cell-h`)은 `html` 규칙의 변수로 정의되어 있으므로, 변수를 다시 정의하면 그 값을 쓰는 곳이 한꺼번에 바뀐다.

```css
html {
  --mdgh-fg: #24292f;
  --mdgh-rule: 1px solid #afb8c1;
}
a { color: #d1242f; }
code { background-color: #fff8c5; }
h1, h2 { color: #0550ae; }
```

- 기본 규칙과 변수는 `themes/base.css` 에 있다. 색 값은 테마 파일(`themes/github-light.json`, `themes/github-dark.json`)에서 채워진다.
- minihtml 이 지원하는 속성만 동작하고, `var()` 는 값 전체에만 쓸 수 있다(`1px solid var(--x)` 는 동작하지 않는다).
- 페이지 배경은 color scheme 의 배경이므로 사용자 CSS 로 바꿀 수 없다.
- 사용자 CSS 의 선언과 변수 정의는 블록마다 다시 처리되므로, 많이 더하면 큰 문서를 그리는 시간이 길어진다. 특히 변수 정의는 일반 선언보다 비용이 크다.

## 한계

- 수식과 mermaid 다이어그램은 렌더하지 않고 원문·코드 블록으로 보인다. SVG 이미지(배지 포함)는 표시하지 않고 대체 텍스트로 보인다.
- 표와 코드 블록은 가로로 스크롤되지 않고 줄바꿈된다.
- 미리보기에서는 텍스트를 선택하거나 복사할 수 없고, 코드 블록 복사 버튼도 없다.
- `<br>`, `<kbd>`, `<sub>`, `<sup>`, `<details>`(항상 펼쳐진 상태), `<img>` 외의 원시 HTML 은 원문 그대로 보인다.
- Sublime Text 에 해당 API 가 없어 탭 제목을 바꾸거나 탭 클릭으로 전환할 수 없다. 버튼은 편집 영역 안에 그려지며 문서와 함께 스크롤된다.
- 밝은 테마에서 첫 줄이 긴 문서는 도구줄 버튼 오른쪽에 회색 점(접힌 원문을 표시하는 Sublime Text 의 fold 표시)이 남는다.
- 다른 패키지 중 일부(MarkdownEditing 등)는 미리보기 화면에 자기 표시를 붙일 수 있다. MarkdownPreviewOverlay 는 같은 파일에 자기 버튼을 그리므로 함께 켜지 않는다.
- 미리보기에 진입하는 시간은 블록 수에 비례하며, 1,000줄 남짓한 문서에서 약 0.3초다. 화면은 조각 단위로 채워지므로 그동안에도 입력이 멈추지 않는다. `max_file_size`(기본 300,000바이트)를 넘는 파일은 미리보기를 거부한다.

## 개발

패키지를 고치거나 fork 하려면 [docs/README.md](docs/README.md) 의 설계 문서를 본다.

## 라이선스

[LICENSE](LICENSE) 를 본다. 동봉한 라이브러리와 아이콘, 테마 값의 출처와 각 라이선스도 같은 파일에 있다.
