"""Creates or updates backend/.env interactively (used by setup_windows.bat; works on any OS).

    python -m scripts.configure_env

Copies .env.example to .env if needed, sets a random SECRET_KEY, and asks three questions:
database (PostgreSQL or SQLite), lecturer invite code, and whether email verification is required.
Existing answers in .env are kept unless you change them. Nothing else in the file is touched."""
import re
import secrets
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ENV, EXAMPLE = HERE / ".env", HERE / ".env.example"


def read() -> str:
    if not ENV.exists():
        shutil.copy(EXAMPLE, ENV)
        print("Created backend/.env from .env.example")
    return ENV.read_text(encoding="utf-8")


def get(text: str, key: str) -> str:
    m = re.search(rf"^{key}=(.*)$", text, re.M)
    return m.group(1).strip() if m else ""


def put(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    if re.search(rf"^{key}=", text, re.M):
        return re.sub(rf"^{key}=.*$", lambda _: line, text, count=1, flags=re.M)
    return text.rstrip("\n") + "\n" + line + "\n"


def ask(q: str, default: str) -> str:
    a = input(f"{q} [{default}]: ").strip()
    return a or default


def main():
    t = read()
    if "change-me" in get(t, "SECRET_KEY") or len(get(t, "SECRET_KEY")) < 32:
        t = put(t, "SECRET_KEY", secrets.token_urlsafe(48))
        print("Set a new random SECRET_KEY.")

    current = get(t, "DATABASE_URL")
    use_pg = ask("Use PostgreSQL? (y = PostgreSQL, n = SQLite file for a quick local run)",
                 "n" if current.startswith("sqlite") else "y").lower().startswith("y")
    if use_pg:
        if current.startswith("sqlite"):
            current = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/adaptiveiq"
        print("PostgreSQL URL format: postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE")
        t = put(t, "DATABASE_URL", ask("PostgreSQL URL", current))
    else:
        t = put(t, "DATABASE_URL", "sqlite:///./adaptiveiq.db")

    code = ask("Lecturer invite code (lecturers type it when they sign up)",
               get(t, "LECTURER_INVITE_CODE") or secrets.token_urlsafe(9))
    t = put(t, "LECTURER_INVITE_CODE", code)

    verify = ask("Require email verification? Without SMTP settings the link appears in the backend window (y/n)",
                 "y" if get(t, "REQUIRE_EMAIL_VERIFICATION").lower() != "false" else "n").lower().startswith("y")
    t = put(t, "REQUIRE_EMAIL_VERIFICATION", "true" if verify else "false")

    ENV.write_text(t, encoding="utf-8")
    print(f"\nSaved {ENV}")
    print(f"Lecturer invite code: {code or '(lecturer sign-up is off)'}")


if __name__ == "__main__":
    main()
