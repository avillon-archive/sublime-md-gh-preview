# 개발

## 개발 설치

Package Control 은 패키지를 레포 이름 `sublime-md-gh-preview` 로 설치하므로, 작업 사본도 같은 이름의 junction 으로 연결한다. junction 을 만들면 실행 중인 Sublime Text 가 바로 플러그인을 읽는다.

```
mklink /J "%APPDATA%\Sublime Text\Packages\sublime-md-gh-preview" C:\path\to\sublime-md-gh-preview
```

- Package Control 설치본과 이름이 같으므로 함께 두지 않는다. Package Control 로 설치해 보기 전에 junction 을 지운다.
- junction 은 `rmdir "%APPDATA%\Sublime Text\Packages\sublime-md-gh-preview"`(재귀 옵션 없이)로만 지운다. 재귀 삭제는 대상 폴더의 내용까지 지운다.
- Package Control 설치본은 zip(`.sublime-package`)이다. 패키지 파일은 `sublime.load_resource` 로 읽고, 패키지 폴더 이름은 `mdgh/theme.py` 의 `PACKAGE` 와 `plugin.py` 의 `__package__` 에서 얻는다.

## 배포 범위

Package Control 은 GitHub 아카이브를 받는다. `.gitattributes` 의 `export-ignore` 경로(`tests/`·`docs/`·`CLAUDE.md` 등)는 아카이브에서 빠진다.

## 테스트

```
python -m pytest -q tests
```

- 시스템 Python 3.14 로 Sublime Text 없이 실행한다. `tests/conftest.py` 가 `lib/` 를 import 경로에 넣는다.
- 대상은 순수 로직이다. 블록 분할이 원문 줄을 빠짐없이 덮는지, slug 가 GitHub 규칙과 같은지(중복 접미사 포함), 편집 링크가 블록의 모든 원문 줄을 올바른 줄 번호로 덮는지(softbreak·표 행·코드 줄), 줄바꿈이 단일 토큰이 아닌 한 최대 폭을 넘지 않는지, 표 열 폭 상한 탐색이 예산을 지키고 단어 최소폭을 보장하는지, 렌더러 출력이 minihtml 허용 목록 안에 있고 블록 phantom 에 `<style>`·글꼴 이름 inline style 이 없는지, 해시 기반 위치 복원이 앞에 블록이 끼어들어도 같은 블록을 찾는지, 모드 기억의 상한과 삭제가 맞는지 등을 검사한다.
- 측정 함수는 가짜 폭 함수로 대체한다. `controller` 처럼 `sublime` 을 import 하는 모듈은 테스트하지 않으므로, 테스트할 계약이 있는 로직은 순수 함수 모듈에 둔다.
- 표본 문서는 `tests/fixtures/sample.md` 다. 지원하는 모든 요소, 긴 줄 1, 넓은 표, 인라인 코드가 든 줄을 포함한다.

## 실렌더 검증

렌더 결과, fold·phantom 배치, 이벤트 처리는 유닛 테스트로 확인할 수 없으므로 실제 Sublime Text 에서 확인한다.

- **격리 인스턴스**: Sublime Text 설치 폴더를 다른 폴더에 복사하고 그 안에 `Data` 폴더를 만들면 portable 인스턴스로 뜬다. 그 사본의 `subl.exe -b --command …` 는 그 인스턴스로만 간다. 인스턴스의 `Data\Packages` 에 개발 설치 junction 을 따로 만든다. 사용자가 쓰는 Sublime Text 의 세션·설정을 건드리지 않고 패키지 명령을 실행하고, 진단 명령으로 블록 y 표·`layout_extent`·viewport 를 로그로 남기고, 그 프로세스의 창만 캡처해 픽셀 수치로 판정할 수 있다.
- 합성 마우스 클릭은 Sublime Text 가 처리하지 않으므로, 클릭·hover 항목은 실제 마우스로 확인한다. 설치된 다른 패키지와의 상호작용도 실제 사용 환경에서 확인한다.
- 표본: `tests/fixtures/sample.md`, 표와 긴 한국어 문단이 있는 실제 문서, 1,000줄 이상의 문서(성능), 빈 파일, 1글자 파일, 빈 줄로 시작하는 파일, 줄 1 이 창보다 긴 파일, 외부 변경 스크립트(끝에 추가, 중간 삽입, 전체 교체).

### 확인 항목

전환과 상태:

- 전환을 왕복한 뒤 버퍼가 dirty 가 아니고, undo 이력이 그대로이고, 설정 유효값이 진입 전과 같다(진입 전에 view 수준 `color_scheme` 이 있던 경우 포함). 미리보기 중에 전역 `color_scheme` 을 바꾼 뒤 복귀하면 새 scheme 을 따른다.
- 사용자 fold 가 있는 상태로 왕복하면 fold 가 그대로다(clone 쪽 편집이 있었어도).
- 빈 파일, 1글자 파일, 빈 줄로 시작하는 파일에서 예외 없이 전환된다.
- Sublime Text 재시작과 패키지 재로드 뒤 미리보기가 복구되고, 접힌 채 남는 view 가 없다. 미리보기로 닫은 파일을 다시 열면 미리보기로, 보던 위치에서 열린다.
- 새 scheme 파일을 만든 직후 진입해도 "Error loading colour scheme" 모달이 뜨지 않는다.

도구줄과 입력:

- 줄 1 이 짧은 문서는 배치 A(도구줄에 fold 마커가 없고 전환해도 버튼이 거의 같은 자리), 줄 1 이 긴 문서는 배치 B 로 그려진다.
- 두 모드의 버튼이 오른쪽 끝에 붙어 있고, 마우스를 올려도 레이아웃이 바뀌지 않는다. 편집 모드에서 줄 1 을 길게·짧게 고쳐도, 줄 1 이 창보다 길어도 버튼이 보인다. 줄 1 끝에서 타이핑하면 글자가 버튼 뒤로 가지 않고 캐럿이 텍스트 끝에 있다.
- 본문 더블클릭으로 그 원문 줄이 같은 화면 높이에 오며 편집 모드가 된다(문단·목록·표 행·코드 줄·이미지). 단일 클릭은 모드를 바꾸지 않는다. 실제 링크는 단일 클릭으로 열리고 더블클릭해도 한 번만 열린다.
- 도구줄 클릭·더블클릭·연속 클릭이 캐럿과 선택을 만들지 않는다. `Ctrl+A` 뒤 타이핑해도, `Ctrl+Z` 를 눌러도 버퍼가 바뀌지 않는다.
- 휠 1노치 이동량이 편집 모드와 같다. 화살표·Page·Home/End·Space 가 스크롤한다.
- 찾기·줄 이동 단축키가 편집 모드로 바꾼 뒤 실행된다. `Ctrl+P`·명령 팔레트·콘솔은 모드를 바꾸지 않는다. Goto Symbol 은 헤딩 panel 을 연다.
- `Ctrl+=`/`Ctrl+-`/`Ctrl+휠` 뒤 미리보기 글자 크기가 따라오고 배치가 다시 맞춰진다.

갱신:

- 외부에서 파일을 바꾸면(끝 추가, 중간 삽입, 전체 교체) 위치를 유지한 채 다시 그린다.
- clone 한쪽의 편집이 다른 쪽 미리보기에 반영되고, 편집 쪽이 읽기 전용이 되지 않으며, 문서 끝에 타이핑해도 미리보기 쪽에 원문이 드러나지 않는다. 줄 1 을 나누는 편집 뒤에도 미리보기가 비지 않는다.

외형:

- 문단 줄 간격이 본문 px × 1.5 ± 1px 다.
- 표의 세로 경계 정렬 오차가 1px 이하이고(헤더 포함), 모든 행에 세로선이 있으며, 가로선의 두께가 한 선 안에서 일정하고, 셀을 줄바꿈한 뒤 행 높이가 맞는다.
- 번호 목록의 둘째 줄이 본문 시작과 정렬되고, 체크 목록 아이콘이 글자 상자 안에 있다.
- 한글·공백이 든 경로의 이미지가 표시되고 크기가 맞는다. 한글이 섞인 하이라이트 코드 줄의 글자 크기가 ASCII 줄과 같다.
- `auto` 가 에디터 scheme 의 밝기를 따르고, scheme 을 바꾸면 다시 판정한다. 다크 테마에서 버튼이 잘 보인다.

다른 패키지:

- 미리보기 view 에 BufferScroll 이 fold·스크롤을 저장하지 않는다(미리보기로 닫은 파일을 `remember_mode` false 로 다시 열어도 접혀 있지 않다).
- LSP, BracketHighlighter, WordingStatus, MarkdownEditing, PlainNotes 가 미리보기 view 에 진단·phantom·region 을 붙이지 않고 콘솔에 예외가 없다. MarkdownEditing 과 PlainNotes 는 `is_widget` 을 확인하지 않으므로 특히 확인한다.

## Sublime Text 업그레이드 때 다시 확인할 동작

이 패키지는 문서화되지 않은 Sublime Text 동작에 기댄다. Sublime Text 를 업그레이드하면 격리 인스턴스에서 아래 동작이 그대로인지 확인한다.

- fold 경계의 phantom: fold 시작 경계의 phantom 은 그려지지 않고, 끝 경계와 point 0 의 phantom 은 그려진다.
- inline 버튼과 block phantom 의 추가 순서·point 규칙([preview-view.md](preview-view.md) §phantom anchor 와 추가 순서).
- 재로드가 fold 와 phantom 을 모두 지운다.
- block phantom 마다 4px 가 더해진다.
- minihtml 의 줄 간격 계산 방식([theme.md](theme.md) §줄 간격).
- phantom 안 `<style>` 이 `phantom_css` 를 이긴다.
- `<img>` 의 `width`·`height` 속성 처리와 `file://` 경로 형식.
- style 속성 안의 작은따옴표가 속성 전체를 무효로 만든다.
- 패키지들의 `is_widget` 관례.
- 도구줄 클릭이 `drag_select` 로 온다. selection 이 빈 view 에는 줄 단위 `move` 가 오지 않는다.
- API 로 연 `show_overlay` 가 `on_window_command` 에 오지 않는다.
- 같은 이름의 scheme 파일을 고쳐 쓰면 약 1초 뒤 다시 읽힌다. 새 scheme 파일을 곧바로 지정하면 오류 모달이 뜬다.
