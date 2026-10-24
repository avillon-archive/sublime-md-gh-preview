# 측정 기반 인라인 레이아웃

minihtml 에는 표 레이아웃과 목록 표식 위치 지정 수단이 없으므로, 글자 폭을 직접 재서 표의 열 폭·셀 줄바꿈과 번호·체크 목록의 hanging indent 를 계산한다. 글머리표 목록(`<ul>`)은 minihtml 이 직접 배치하므로 측정하지 않는다.

## 측정 panel

- 창마다 숨김 output panel(`create_output_panel(name, unlisted=True)`)을 글꼴 종류별로 둔다. 종류는 본문, 본문 굵게, 고정폭이다(`layout.FONT_KINDS`). 이 panel 은 절대 `show_panel` 하지 않는다.
- panel 설정은 `layout._PANEL_SETTINGS` 다. `font_size` 는 CSS px × 0.75 로 두고, 줄바꿈·gutter·여백·줄 padding 을 모두 끈다. 잴 텍스트를 줄마다 하나씩 한 번에 넣고 `text_to_layout` 의 차이로 폭을 잰다.
- 굵은 글꼴은 처음부터 `font_face` 를 `<본문 글꼴> Bold` 로 만든 panel 로 잰다. 이 값은 렌더된 굵은 글자 폭과 px 단위로 같다. 굵게 scheme(`font_style: bold`)을 건 panel 은 regular 와 같은 폭을 내므로 쓰지 않는다.
- 같은 panel 의 `font_face` 를 바꿔 가며 재지 않는다. 바꾼 직후의 측정값이 비정상이므로 글꼴 종류마다 panel 을 따로 만든다.
- 기울임 글자는 본문 글꼴 panel 로 잰다. 차이는 여유폭 `layout.SAFETY` 가 흡수한다.
- 측정 panel 의 `font_face` 와 CSS `font-family` 의 첫 항목이 같아야 측정이 맞는다. 그래서 글꼴 설정(`font_body`·`font_mono`)은 대체 목록이 아닌 단일 글꼴 이름이다.

## 측정 규칙

- block phantom 의 폭은 `viewport_extent()[0] − 12px` 이다. 가용 폭은 이 폭에서 블록의 좌우 padding 을 뺀 값이다.
- 측정 폭은 정수 px 로 양자화된다. 줄바꿈 판단은 캐시된 토큰(단어·공백·코드 span) 폭의 산술로 하고, 확정된 줄은 줄 전체 문자열로 다시 재서 열 폭에 쓴다. 토큰 폭을 합산하면 양자화 오차가 쌓이기 때문이다.
- 측정 캐시의 키는 (텍스트, 글꼴 종류, 크기)다. 테마·글꼴·크기 설정이 바뀌면 비운다. 창이 닫힐 때(`on_pre_close_window`) 그 창의 panel 을 `destroy_output_panel` 하고 캐시를 지운다.
- 규모: 토큰 폭은 (텍스트, 글꼴)마다 한 번만 재고, 열 폭 상한의 이분 탐색은 캐시값의 산술로만 실행한다. panel 에는 측정할 문자열을 모아 한 번에 넣는다.
- 정렬·폭 계산 함수(`wrap_tokens`·`table_budget`·`column_caps`·`align_pads`·`marker_pads` 등)는 측정값이나 측정 함수를 인자로 받는 순수 함수다. 테스트는 가짜 폭 함수로 이 함수들을 검사한다.

## 번호 목록과 체크 목록

- 표식을 글자 흐름 밖에 둘 수단이 없으므로 측정이 필요하다. 높이 0 표식(`line-height: 0` div)도 한 줄 높이를 차지해 첫 줄을 밀어 내리고, 흐름 안의 표식은 `position: relative` 로 옮겨도 그 폭만큼 첫 줄을 민다. 음수 `margin`, `text-indent`, `list-style-type: none`·`decimal` 은 minihtml 에 없다.
- 그래서 번호 마커와 본문을 각각 inline-block 으로 두고, 본문 폭을 측정해 줄바꿈한 결과로 hanging indent 를 만든다.
- 체크 아이콘: minihtml 은 line-height 가 있는 줄의 `<img>` 를 세로로 늘린다. 그래서 아이콘 줄은 자연 높이 div 에 두고 `position: relative; top` 으로 글자 상자 안으로 내리며, 여러 줄 항목의 나머지 표식 줄에만 본문 줄 높이를 준다. span 에 `position: relative` 를 주면 이미지가 잘리므로 div 에 준다.

## 표

- 행 div 에 `padding: 7px 0 6px`(마지막 행은 아래 7px)을 두고, 표 끝에 `padding-bottom: 8px` 을 둔다. minihtml 은 inline-block 의 세로 padding·border 를 줄 높이에 넣지 않으므로 행 div 가 그 자리를 만든다.
- 셀은 `padding: 6px 13px` 에 `border-top`·`border-left` 를 두고, 마지막 열에 `border-right`, 마지막 행에 `border-bottom` 을 더한다. 짝수 본문 행에 배경을 칠하고, 헤더는 굵게 그린다.
- 세로 테두리 색은 가로 테두리 색과 한 단위 다르게 둔다(예: 가로 `#d1d9e0`, 세로 `#d1d9e1`). 두 색이 같으면 minihtml 이 `border-left` 를 그리지 않는다. 테마 파일에 `table-border-v` 가 없으면 `theme` 이 `table-border` 를 한 단위 바꾼 값으로 채운다.
- 표의 모든 줄 맨 앞에 strut 을 넣는다. strut 은 코드 글꼴의 폭 0 문자 뒤에 본문 글꼴의 폭 0 문자를 둔 것이다(`render.STRUT`). 코드 span 이 든 셀만 기준선이 달라 셀이 1px 어긋나고 가로선이 계단처럼 두꺼워지는 현상과, 코드 글꼴 글자만 있는 셀이 줄 높이가 낮아 처지는 현상을 막는다.
- 가로선을 행 div 에, 바깥 테두리를 컨테이너에 그리는 방식은 쓰지 않는다. 셀 내용이 처지고 세로선이 행 높이를 채우지 못한다.
- 열 폭은 셀 끝에 넣은 투명 PNG(`width` = 열 폭 + SAFETY, `height` = 1)로 강제한다. 왼쪽 정렬 셀에는 padding 을 넣지 않는다.
- inline-block 안에서 `text-align` 을 쓰면 안 된다. inline-block 이 가용 폭 전체로 늘어난다. 오른쪽·가운데 정렬은 줄별 div 의 좌우 padding 으로 만든다.
- 표 전체 폭이 가용 폭을 넘으면 열 폭 상한을 이분 탐색해(단어 최소폭은 보장한다) 셀을 줄바꿈한다. 한 행 안의 셀들은 빈 줄을 채워 줄 수를 맞춘다.
- 셀 안의 인라인 요소는 텍스트, 굵게, 기울임, 코드, 링크, 취소선이다.
