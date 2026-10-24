# sublime-md-gh-preview

Sublime Text 4 패키지 Markdown GitHub Preview 의 레포다.

- 사용자용 설명은 `README.md` 가 갖는다. 패키지 내부 사항을 적지 않는다.
- 설계·사양, 이름 규칙, 개발 설치·검증 절차는 `docs/` 가 갖고 `docs/README.md` 가 색인한다. 동작을 바꾸면 해당 문서를 함께 고친다.
- `docs/plan/`·`docs/investigation/`·`tools/`(아이콘 생성·벤치 같은 로컬 도구)는 gitignored 다. 커밋되는 문서와 주석은 이 경로를 가리키지 않는다.

## 테스트

```
python -m pytest -q tests
```
