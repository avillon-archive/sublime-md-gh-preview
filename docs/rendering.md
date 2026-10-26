# 렌더링

원문을 블록 phantom 의 minihtml 로 바꾸는 과정이다. 측정이 필요한 배치(표·번호 목록·체크 목록)는 [layout.md](layout.md), 스타일 값은 [theme.md](theme.md) 가 설명한다.

## 파이프라인

`blocks`(파싱·블록 분할·slug·해시) → `render`(토큰 → minihtml) → `layout`(측정 기반 줄바꿈) → `controller`(fold·phantom·y 표·갱신 일정).

- **스레드**: 파싱, 블록 분할, 해시는 worker(`sublime.set_timeout_async`)에서 실행한다. 렌더, 측정, 하이라이트(숨김 panel 을 쓴다)와 fold·phantom·viewport 조작은 main thread 에서 실행하되, 조각 하나가 `controller.CHUNK_S` 를 넘지 않게 끊어 `sublime.set_timeout(…, 0)` 으로 이어 붙이고 그 사이에 UI 를 돌려준다. 첫 조각은 바로 실행한다. panel·phantom 을 다루는 일은 worker 로 옮기지 않는다. worker 에서 같은 API 를 부르면 main thread 보다 훨씬 느리다.
- **세대 번호**: view 마다 두고, 새 변경·폭 변경·모드 종료 때 올린다. 조각은 시작할 때 세대를 확인하고, 바뀌었으면 중단한다.
- **보류 위치**: 진입·갱신·재로드·링크가 넘기는 목표 위치다. 목표 블록 번호는 새 문서를 적용할 때 세대마다 한 번 정하고, 조각마다 하는 확인은 그 블록과 그 아래 한 화면이 그려졌는지만 본다.
- **블록 분할**: 최상위 블록 토큰 단위로 나누고, 토큰 `map` 의 원문 줄 범위를 보존한다.
- **블록 html 캐시**: 키는 (블록 원문, 블록 시작 줄, 그 블록이 쓰는 문서 전역 값, 렌더 문맥)이다. 문서 전역 값은 각주 번호와 원격 이미지 해석 결과이고, 렌더 문맥은 폭·테마·글자 크기다. 편집 링크가 절대 줄 번호를 담으므로 키에 시작 줄이 들어간다. 줄을 넣으면 그 아래 블록의 캐시가 모두 무효가 되지만, phantom 을 제자리에서 바꾸는 API 가 없어 바뀐 블록부터 끝까지 다시 추가하는 일은 어차피 필요하다. 캐시가 항목 수 상한(`controller._HTML_CACHE_LIMIT`)에 닿으면 전부 비운다.

## 렌더러

phantom 하나는 `<body id="mdgh"><div class="…">…</div></body>` 다.

- **블록 phantom 안에 `<style>` 을 넣지 않는다.** 스타일은 미리보기 scheme 의 `phantom_css` 가 갖고, phantom 에는 폭에 따라 달라지는 값(가운데 정렬 padding, 표 열 폭, 목록 줄바꿈 결과, 이미지 크기)만 inline `style`·속성으로 넣는다. phantom 안의 `<style>` 은 선택자 특이도와 상관없이 `phantom_css` 를 이기므로, 섞어 쓰면 사용자 CSS 로 덮을 수 없는 규칙이 생긴다. 예외는 도구줄 버튼 phantom 이다. 편집 모드에서는 view 가 사용자 scheme 으로 그려져 `phantom_css` 를 쓸 수 없으므로 버튼 phantom 은 자기 `<style>` 을 갖는다.
- inline `style` 속성에 글꼴 이름을 넣지 않는다. 작은따옴표로 감싼 글꼴 이름이 든 style 속성은 통째로 무시되어 크기와 색도 적용되지 않는다. 글꼴은 `phantom_css` 의 class 규칙으로 지정한다.
- 렌더러 출력은 minihtml 이 지원하는 태그와 CSS 속성만 쓴다. 허용 목록은 `render.ALLOWED_TAGS`·`render.ALLOWED_CSS_PROPS` 이고, 테스트가 출력이 이 목록 안에 있는지 검사한다.

minihtml 이 지원하지 않는 GitHub 요소의 대체 표현:

| GitHub 요소 | minihtml 표현 |
|---|---|
| `<table>` | 행 = block div, 셀 = inline-block span. [layout.md](layout.md) §표 |
| `<ul>` | 그대로 쓴다. minihtml 의 `<ul>` 은 줄바꿈된 줄을 첫 줄 글자 시작에 맞춘다. 중첩 단계별 `list-style-type` 은 disc → circle → square, 들여쓰기는 GitHub 의 2em 이다(minihtml 기본은 단계당 40px) |
| `<ol>`(minihtml 은 번호를 그리지 않는다) | 번호 마커 inline-block + 본문 inline-block(측정 기반 hanging indent). [layout.md](layout.md) §번호 목록과 체크 목록 |
| 체크박스 `<input>` | 아이콘 PNG(light/dark) 마커 + 같은 hanging indent |
| alert(`> [!NOTE]` 등 5종) | 왼쪽 막대 div + 아이콘 PNG 와 종류 이름의 제목 줄(alert 색) |
| 각주 | 참조는 작은 글자에 `position: relative; top` 으로 올린 `[n]` 링크다. 문서 끝 각주 목록은 번호 목록과 같은 배치에 되돌아가는 `↩` 링크를 붙인다. 각주 하나가 블록 하나다 |
| `text-decoration: line-through` | 바깥 span `position: relative; top: -0.55em; border-bottom: 1px solid`, 안쪽 span `top: 0.55em` |
| `<hr>` | div `border-bottom` |
| `<pre>` | div `white-space: pre-wrap` |
| 이미지 | §이미지 |
| 최대 폭(980px 중앙 정렬) | `max-width` 가 없으므로 렌더할 때 뷰포트 폭으로 좌우 padding 을 계산한다(`content_max_width` 설정) |
| font-weight 600(제목·표 헤더) | minihtml 은 normal·bold 만 지원하므로 bold 로 그린다 |

- **블록 사이 세로 간격**은 GitHub 의 margin 겹침 결과를 블록 wrapper 의 padding 으로 재현한다. 기본은 블록 아래 16px 이고, 제목은 위 24px(앞 블록 아래 16px 와 겹치므로 8px 를 더한다), 첫 블록은 위 여백 0 이다. 값은 GitHub 16px 본문 기준이며 본문 크기에 비례한다. Sublime Text 가 block phantom 마다 더하는 4px 는 이 값에서 뺀다.
- block div 의 `text-align`(left·right·center)은 phantom 폭을 기준으로 동작한다. inline-block 안에서는 쓰지 않는다([layout.md](layout.md) §표).
- **heading slug** 는 GitHub 규칙을 따른다. 소문자로 바꾸고, 글자·숫자·`-`·공백 외의 문자를 지우고, 공백을 `-` 로 바꾼다. 중복이면 `-1`, `-2` 접미사를 붙인다.
- 중첩 번호 목록의 표식은 목록 깊이(글머리표 목록 포함) 2 에서 lower-roman, 3 이상에서 lower-alpha 다(GitHub 의 `ul ol`·`ol ol` 규칙).
- 실제 링크에는 `title` 속성으로 대상을 준다. 마우스를 올리면 대상이 툴팁으로 보인다.
- **흐르는 텍스트에서 인라인 코드·`<kbd>` 상자 끝에 공백 없이 글자가 붙어 있으면**(`` `x`, `` · `` 기록(`x`)·y ``) 상자 바로 뒤에 1px 글꼴의 공백(`render.CODE_BREAK`)을 넣는다. minihtml 은 상자가 줄에 들어가면 배경을 그 자리에 그린 뒤, 붙은 꼬리가 넘쳐 단어 전체가 다음 줄로 가도 배경을 윗줄에 남긴다. 이 공백이 꼬리만 다음 줄로 넘기므로, 그 경우 다음 줄이 구두점으로 시작할 수 있다. U+200B 는 minihtml 의 줄바꿈 위치가 되지 않는다. 측정 레이아웃(표·번호 목록·체크 목록)은 줄을 직접 나누므로 넣지 않는다.

## 편집 링크

미리보기 본문을 더블클릭하면 그 원문 줄에서 편집 모드가 된다. 이를 위해 렌더러는 모든 텍스트 런을 그 런이 속한 원문 줄의 `<a class="e" href="mdgh:e:<줄>">` 로 감싼다.

- 줄 번호: 문단·제목·목록 항목·인용·alert·각주는 블록 `map` 의 시작 줄에 앞선 softbreak·hardbreak 수를 더한다. 표는 행(`tr`)의 `map`, 코드 블록은 fence 시작 줄 + 1 + 코드 줄 번호다. 이미지도 감싼다(링크 안의 이미지는 제외한다).
- 실제 링크 런은 감싸지 않는다(`<a>` 를 중첩하지 않는다).
- `a.e` 는 주변 글자와 같은 색에 밑줄이 없다. 감싼 결과는 감싸지 않은 결과와 픽셀 단위로 같아야 한다(굵게·기울임·인라인 코드·하이라이트 span·줄바꿈되는 코드 줄 포함). 감싼 텍스트 위의 마우스 커서는 손 모양이 되는데, minihtml 은 커서를 바꿀 수 없다.
- 더블클릭 판정은 [interaction.md](interaction.md) §더블클릭 이 설명한다.

## 원시 HTML

- HTML 주석(`<!-- -->`, 블록·인라인)은 그리지 않는다.
- 부분집합 `<br>`, `<kbd>`, `<sub>`/`<sup>`, `<details>`/`<summary>`, `<img>` 를 그린다(`render.HTML_SUBSET`). 부분집합 태그가 없는 html_block 은 원문을 이스케이프한 코드 상자로 보인다. 부분집합 태그가 있는 html_block 은 흐르는 텍스트로 그리고, 그 안의 부분집합 밖 태그는 이스케이프한 텍스트로 남긴다. 짝이 없는 닫는 태그는 버리고, 닫히지 않은 태그는 끝에서 닫는다.
- `<details>` 는 항상 펼친 상태다. 여는 html_block 이 `<summary>`(없으면 `Details`) 제목 줄 블록이 되고(아래 간격 0), 그 안의 Markdown 은 그대로 최상위 블록으로 남으며, `</details>` 만 있는 html_block 은 블록 목록에서 뺀다. 한 블록으로 합치면 안쪽 제목이 heading 블록이 아니게 되어 slug·Goto Symbol·앵커·위치 복원·블록 캐시가 깨지므로 합치지 않는다.
- `<kbd>` 는 code 글꼴·크기의 테두리 상자이고, 측정 경로를 code 와 공유한다.

## front matter

- 키를 헤더 행으로, 값을 한 행으로 둔 표로 그린다(표 렌더 경로를 공유한다).
- `frontmatter` 모듈은 의존성 없이 YAML 부분집합(최상위 `key: scalar`, 따옴표 문자열, 인라인·블록 리스트)을 읽는다. 리스트는 항목당 한 줄로 그리고, 부분집합 밖의 값은 고정폭 원문으로 그린다. 최상위가 매핑이 아니면 front matter 전체가 코드 블록으로 보인다.

## 코드 하이라이트

- 창마다 테마 종류(light/dark)별로 숨김 output panel 을 두고, 펜스 info 의 언어로 syntax 를 지정한다(`find_syntax_for_file("x.<ext>")`, 별칭은 `highlight.ALIASES`). 설치된 Sublime Text syntax 전부가 대상이다. 언어별로 panel 을 따로 두지 않는다.
- panel 의 color scheme 은 동봉한 GitHub 코드 팔레트(prettylights, `schemes/github-code-<종류>.hidden-color-scheme`)다. `extract_tokens_with_scopes` 와 `style_for_scope` 로 색·굵게·기울임 span 을 만들고, 토큰 사이의 빈틈 텍스트도 보존한다.
- 캐시 키는 (언어, 코드 텍스트)다. 갱신할 때 바뀌지 않은 코드 블록은 panel 을 쓰지 않는다.
- 언어가 없거나 알 수 없으면 단색으로 둔다. 긴 줄은 `pre-wrap` 으로 줄바꿈한다.
- 한글이 섞인 줄은 따로 처리하지 않는다. 한글은 OS 대체 글꼴로 그려지고, 같은 줄의 ASCII 글자 크기는 한글이 없는 줄과 같다.

## 이미지

### 로컬 이미지

- PNG, JPG, GIF 만 표시한다. `src` 는 `file://` 에 절대 경로를 붙인 값이다(역슬래시는 슬래시로 바꾸고 percent-encoding 은 하지 않는다. 예: `file://C:/docs/img/한글 이름.png`). `Path.as_uri()`(`file:///` + percent-encoding)와 인코딩하지 않은 `file:///C:/…` 는 표시되지 않는다.
- `width`·`height` 속성을 둘 다 준다. `height` 가 없으면 줄 상자가 이미지 높이만큼 커지지 않아 한 줄 높이로 잘린다. 크기는 파일 헤더(PNG IHDR, GIF, JPEG SOF)에서 읽어 본문 폭에 맞게 줄인다.
- 표시 크기는 가로·세로 모두 `navigation.MAX_IMAGE_PX` 이하로 줄인다(비율 유지). 헤더 크기와 `width`·`height` 속성은 문서가 정하는 값이라, 상한이 없으면 phantom 하나가 레이아웃할 수 없을 만큼 커진다. 긴 숫자열 속성은 `inf` 로 읽히므로 무시한다.
- 이미지는 `<span class="im">`(`line-height: 1px`)으로 감싼다. line-height 가 있는 줄에 맨 `<img>` 를 두면 2px 크게 그려진다.
- 상대 경로는 문서 파일이 있는 폴더를 기준으로 푼다. 절대 경로·드라이브 경로·UNC 경로는 열지 않는다([interaction.md](interaction.md) §링크 와 같은 제약). 파일 경로가 없는 버퍼, 없는 파일, SVG 는 alt 텍스트로 보인다.
- 이미지 파일은 정규 파일만 연다. `CON`·`NUL` 같은 장치 이름을 열면 main thread 가 멈춘다.
- 패키지 이미지의 `src` 는 `res://Packages/<패키지 폴더>/...` 다. 접두사 없는 `Packages/...` 는 깨진 이미지로 보인다. `<img>` 의 `padding` 은 무시되므로 이미지 옆 간격은 이웃 span 의 padding 으로 준다.
- 아이콘 PNG(버튼·체크박스·alert)는 Octicons 경로를 그린 이미지이고, 표시 크기의 2배로 만들어 두고 `width`·`height` 에 표시 크기를 준다. minihtml 이 필터링해 줄이므로 부드럽게 보인다. 같은 크기로 그려도 세로 보간이 생겨 1px 선이 흐려지므로 아이콘은 굵은 획으로 그린다. 생성 스크립트는 레포에 포함하지 않는다.

### 원격 이미지

`remote_images` 가 true 일 때만 http(s) 이미지를 내려받는다. false 이면 원격 이미지는 alt 텍스트 링크로 보인다.

- 패키지가 소유한 스레드 풀(`remote.WORKERS`)에서 받아 `cache_path()/<패키지 폴더>/images/<sha1(url)>.<ext>` 에 둔다. 파일 크기(`remote.MAX_BYTES`), 전체 시간(`remote.TIMEOUT_S`), 캐시 총량(`remote.CACHE_LIMIT`)에 상한이 있고, 형식은 내용의 헤더로 판별한다.
- 다 받으면 그 URL 을 쓰는 미리보기만 갱신한다. 실패한 URL 은 세션 동안 다시 받지 않는다. 받는 상태(`loading`·`failed`·`paths`)는 main thread 에서만 바꾼다.
- `set_timeout_async` 로 받지 않는다. Sublime Text 의 async 콜백은 한 스레드에서 차례로 실행되므로, 느린 호스트의 이미지가 파싱과 다른 패키지의 async 이벤트를 이미지마다 최대 시간 상한까지 막는다.
