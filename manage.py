#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def _load_dotenv_local():
    """Load repo-root .env.local before choosing settings (host-only dev overrides)."""
    path = os.path.join(os.path.dirname(__file__), ".env.local")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


def main():
    """Run administrative tasks."""
    _load_dotenv_local()

    # Unit tests use SQLite + locmem email (see tfk_mentors/test_settings.py).
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        os.environ["DJANGO_SETTINGS_MODULE"] = "tfk_mentors.test_settings"
    else:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tfk_mentors.settings")

        # Match wsgi.py: use production.py on deploy servers when present.
        # Local dev with a copied production.py: set TFK_LOCAL_DEV=1 in .env.local.
        production_settings = os.path.join(
            os.path.dirname(__file__), "tfk_mentors", "production.py"
        )
        if (
            os.path.isfile(production_settings)
            and os.environ.get("TFK_LOCAL_DEV") != "1"
            and os.environ.get("DJANGO_SETTINGS_MODULE") != "tfk_mentors.test_settings"
        ):
            os.environ["DJANGO_SETTINGS_MODULE"] = "tfk_mentors.production"

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
