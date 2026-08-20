# tfk-mentors

App to manage mentors at practice.

## Dev environment

```bash
docker compose up -d --build
```

- API: http://localhost:8000
- Frontend: http://localhost:5173

## Django unit tests

Tests use SQLite + the locmem email backend via `tfk_mentors/test_settings.py` (selected automatically when you run `manage.py test`).

### Run all tests (Docker)

```bash
docker compose exec -T web python manage.py test -v1
```

### Run one module

```bash
docker compose exec -T web python manage.py test tfk_mentors.tests.test_underfilled_pace_email -v1
```

### Measured coverage

```bash
docker compose exec -T web coverage erase
docker compose exec -T web coverage run --source=tfk_mentors,tasks manage.py test -v0
docker compose exec -T web coverage report -m
```

Config lives in `.coveragerc` (omits migrations, settings bootstrap, wsgi/asgi, tests).

### Host venv (optional)

```bash
.venv/bin/python manage.py test -v1
.venv/bin/coverage run --source=tfk_mentors,tasks manage.py test -v0
.venv/bin/coverage report -m
```
