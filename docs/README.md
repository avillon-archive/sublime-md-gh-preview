# 설계 문서

Markdown GitHub Preview 를 유지보수하거나 fork 해서 고치는 사람을 위한 설계·사양 문서다. 설치와 사용법은 레포 루트의 `README.md` 가 설명한다.

| 문서 | 내용 |
|---|---|
| [preview-view.md](preview-view.md) | 미리보기 화면을 view 안에 만드는 구조(fold·phantom·y 표), 모드 상태 저장과 복구, 모드 기억 |
| [rendering.md](rendering.md) | 렌더 파이프라인, 토큰 → minihtml 렌더러, 편집 링크, 원시 HTML, 코드 하이라이트, 이미지 |
| [layout.md](layout.md) | 글자 폭 측정에 기반한 표·번호 목록·체크 목록 배치 |
| [theme.md](theme.md) | 테마 변수와 CSS, 미리보기 color scheme, 글자 크기와 확대·축소 |
| [interaction.md](interaction.md) | 도구줄 버튼, 전환 수단, 미리보기 입력 처리, 스크롤 동기화, 링크 |
| [updates.md](updates.md) | 편집·재로드·폭 변경에 따른 다시 그리기 |
| [development.md](development.md) | 개발 설치, 테스트, 실렌더 검증, Sublime Text 업그레이드 때 다시 확인할 동작 |

## 목표

한 탭 안에서 원문 편집 모드와 GitHub 스타일 미리보기 모드를 전환한다. 외부 브라우저, 별도 창, 전용 side-by-side 화면은 쓰지 않는다.

- 미리보기 외형은 github.com 의 markdown-body 를 따른다. 스타일 값의 출처는 `github-markdown-css`(sindresorhus)이고, 버전은 각 테마 파일(`themes/*.json`)의 `_source` 필드에 적혀 있다.
- 미리보기는 같은 view 의 상태 전환이다. 버퍼 내용, dirty 상태, undo 기록은 전환으로 바뀌지 않는다.
- 파일마다 마지막 모드와 위치를 기억하고, 외부 변경과 clone view 의 편집을 미리보기에 반영한다.
- 설정 키와 기본값은 `Markdown GitHub Preview.sublime-settings` 의 주석이 정의한다.

범위 밖:

- mermaid·수식 렌더, SVG 이미지(배지 포함), 표와 코드의 가로 스크롤(줄바꿈으로 대신한다).
- 미리보기에서 텍스트 선택·복사, 코드 블록 복사 버튼, 미리보기 안 찾기(찾기는 편집 모드로 바꾼 뒤 원문에서 실행한다).
- 탭 제목 변경, 탭 클릭으로 전환, 탭 안 버튼. Sublime Text 에 해당 API 가 없다. `View.set_name` 은 탭 제목을 바꾸지만 파일 연결을 끊으므로 쓰지 않는다.

## 지원 환경

- Sublime Text build 4213 이상의 Python 3.14 플러그인 호스트에서 동작한다(`.python-version` = `3.14`). 동봉한 markdown-it-py 4.x 가 Python 3.10 이상을 요구하므로 Python 3.8 호스트는 지원하지 않는다.
- 개발과 검증은 build 4215, Windows 11, 96 DPI 에서 했다. 로컬 이미지의 `file://` 경로 형식, 플랫폼별 기본 글꼴, 굵은 글꼴 이름(`<글꼴> Bold`)은 Windows 에서만 실측했으므로 다른 OS 에서는 확인이 필요하다.

## 핵심 설계 결정

- **렌더 엔진은 Sublime Text 내장 minihtml 이다.** WebView 창을 편집 영역 위에 겹치는 방식은 쓰지 않는다. 그 방식은 명령 팔레트·자동완성·Goto 오버레이를 가리고, 창 크기와 사이드바 변경 이벤트가 없어 위치를 폴링해야 하며, 키보드 포커스를 가져가 단축키를 끊는다.
- **원문을 fold 로 감추고 그 자리에 블록 단위 phantom 을 그린다.** 구조는 [preview-view.md](preview-view.md) 가 설명한다.
- **읽기 전용 플래그를 쓰지 않는다.** `View.set_read_only` 는 버퍼 단위라서 같은 버퍼의 clone view 까지 편집할 수 없게 만든다. 미리보기 view 는 "selection 이 항상 비어 있다" 는 불변식과 명령 가로채기로 편집을 막는다([interaction.md](interaction.md) §미리보기 입력 처리).
- **미리보기 view 에 `is_widget: true` 를 둔다.** 패키지들이 위젯 view 를 건너뛰는 관례를 이용해, 미리보기 상태(fold·스크롤·빈 selection)가 다른 패키지의 동작과 저장소에 닿지 않게 한다. BufferScroll, LSP, BracketHighlighter, WordingStatus, Default 패키지의 jump history·들여쓰기 감지가 이 설정을 보고 view 를 건너뛴다. 이 설정을 둔 파일 view 에서 Sublime Text 코어 동작(포커스·이벤트·sheet·창 안 위치)이 바뀌는 현상은 관측되지 않았다.
- **파서**: markdown-it-py·mdurl·mdit-py-plugins 를 버전을 고정해 `lib/` 에 동봉하고(순수 Python, 각 LICENSE 포함), `plugin.py` 가 이 경로를 `sys.path` 맨 앞에 둔다. 다른 패키지가 같은 이름의 모듈을 먼저 import 해 두었으면 그 항목을 `sys.modules` 에서 빼고 동봉본을 import 한다. 파서 구성은 `MarkdownIt("commonmark").use(gfm_plugin, front_matter=True)` 하나다. 표·취소선·체크 목록·alert 는 markdown-it-py 의 내장 옵션이, GFM autolink·각주·front matter 는 mdit-py-plugins 가 처리한다. 패키지가 직접 구현하는 것은 minihtml 렌더러와 heading slug 다. 렌더러는 HTML 을 거치지 않고 토큰에서 minihtml 을 바로 만든다.
- **MarkdownPreviewOverlay 와 함께 켜는 것은 지원하지 않는다.** 그 패키지는 같은 파일에 자기 버튼을 그려 본문을 민다.

## 이름

- 표시 이름은 `Markdown GitHub Preview`, 줄임말은 `MD GH Preview` 다. 표시 이름을 `MdGh` 로 줄여 쓰지 않는다.
- 레포와 Package Control 패키지 폴더 이름은 `sublime-md-gh-preview` 다.
- 코드 식별자는 `mdgh` 로 통일한다. 클래스는 `MDGHPreview*`(Sublime Text 가 여기서 명령 이름 `mdgh_preview_*` 를 만든다), view 설정·region·keymap context 키는 `mdgh_preview.*`, 모듈은 `mdgh`, CSS 는 `#mdgh`·`--mdgh-*` 다.
- 패키지 리소스 경로(`Packages/<폴더>/...`)는 `mdgh/theme.py` 의 `PACKAGE` 상수에서 만든다. 경로에 패키지 이름을 직접 적지 않는다.

## 모듈 구조

```
plugin.py            Sublime Text 진입점: plugin_loaded/unloaded, 명령, 이벤트 리스너(controller 에 위임)
mdgh/
  controller.py      view 별 모드 전환, 설정 스냅숏, fold·phantom·y 표, 복구, 갱신 일정(세대·조각)
  blocks.py          파싱, 최상위 블록 분할(원문 줄 범위), slug, 블록 해시
  render.py          토큰 → minihtml, 편집 링크
  layout.py          측정 panel, 줄바꿈, 표·번호 목록·체크 목록 배치, fold 배치·버튼 위치 계산
  highlight.py       코드 하이라이트와 캐시
  theme.py           테마 변수, phantom_css 조립, 미리보기 scheme 생성, auto 판정
  navigation.py      링크·앵커·이미지 경로 해석, 스크롤 동기화 계산
  input.py           미리보기 입력 처리(명령 분류, 더블클릭 판정, 키 스크롤 목표)
  modestore.py       파일별 모드·위치 기억
  frontmatter.py     front matter 의 YAML 부분집합 읽기
  remote.py          원격 이미지 내려받기와 캐시
themes/              github-light.json, github-dark.json(테마 변수), base.css(CSS 템플릿)
schemes/             코드 하이라이트용 hidden color scheme(light/dark)
icons/               버튼·체크박스·alert PNG(표시 크기의 2배)
lib/                 markdown_it, mdurl, mdit_py_plugins
tests/               pytest(Sublime Text 없이 실행되는 순수 로직)
```

`controller` 는 모듈 맨 위에서 `sublime` 을 import 하므로 테스트에서 import 할 수 없다. 위치 계산처럼 테스트할 계약이 있는 로직은 `navigation`·`input`·`layout` 같은 순수 함수 모듈에 두고 그 경계에서 테스트한다.
