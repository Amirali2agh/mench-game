# Contributing

## Branch and pull request flow

`main` is protected by process: never commit or push to it directly.

```bash
git fetch origin
git checkout -b fix/short-description origin/main
# ... work ...
git push -u origin fix/short-description
# open a pull request against main
```

Branch prefixes: `fix/`, `feat/`, `chore/`, `docs/`, `refactor/`.

* One topic per commit, English commit messages.
* Reference the issue in the commit body (`Refs #12`) and close it from the pull
  request body (`Closes #12`).
* Keep pull requests small; a reviewer must be able to read the whole diff.
* Merge only when every gate below is green. Do not merge your own pull request
  without the automated gates passing.

## Gates

Run all of them before every commit:

```bash
python -m pytest -q

cd front
npx tsc --noEmit
npm run lint
npm test
npx vite build
```

CI (`.github/workflows/ci.yml`) runs the same commands, one job each, plus a
secret scan. A red gate is a merge blocker.

## Tests

* A bug fix starts with a failing test that reproduces the bug, then the fix,
  then the test goes green.
* Tests use the in-memory Redis fake in `test/conftest.py`; they must not need a
  running Redis.
* Engine and board-geometry changes need a test. Do not change Mensch rules,
  safe/home cells, win conditions or corner offsets without one.

## Code style

* Python: type hints, no `print()`, use `logging`. Avoid bare `except`.
* TypeScript: strict mode, no `any` (use `unknown` and narrow), no `console.log`.
* No `TODO`/`FIXME` in committed code; open an issue instead.
* Keep UI text Persian and right-to-left. Code, comments and commit messages are
  English.
* UI text lives in the components and is Persian; numbers shown to players use
  Persian digits where the existing components already do.
* Preserve the line endings of files you touch. Several files are CRLF or mixed;
  a whole-file rewrite that flips them creates a fake multi-thousand-line diff.
  Use a targeted edit instead.
* Never commit `node_modules`, build output, `.env` files or credentials.

## Security

* Never commit an API key, token or password. Configuration comes from the
  environment (`.env.example` documents every variable).
* Treat every `playerId`/`roomId` from the client as untrusted input.
* Do not add a development or cheat endpoint that is reachable without
  `DEBUG=true`.
