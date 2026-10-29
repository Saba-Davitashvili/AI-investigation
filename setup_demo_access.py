"""Enable the demo password without replacing an existing Groq key."""
import argparse
import os
import re
import secrets

from config import BASE_DIRECTORY


def update_assignments(text, updates):
    lines = text.splitlines()
    pending = dict(updates)
    result = []
    for line in lines:
        key = line.partition("=")[0].strip()
        if key in updates:
            if key in pending:
                result.append(key + "=" + pending.pop(key))
        else:
            result.append(line)
    result.extend(key + "=" + value for key, value in pending.items())
    return "\n".join(result) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--host", help="Public DNS hostname, without https://")
    args = parser.parse_args()
    if args.host and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]", args.host):
        parser.error("Supply a DNS hostname, without a scheme, path or port.")
    path = BASE_DIRECTORY / ".env"
    if not path.exists():
        raise SystemExit("Create .env from .env.example and set GROQ_API_KEY first.")
    from dotenv import dotenv_values
    existing = dotenv_values(path)
    password = existing.get("DEMO_PASSWORD") or os.getenv("DEMO_PASSWORD")
    generated = not password or password.startswith("replace")
    if generated:
        password = secrets.token_urlsafe(24)
    updates = {"DEMO_USERNAME": existing.get("DEMO_USERNAME") or "reviewer", "DEMO_PASSWORD": password}
    if args.production:
        updates["APP_ENV"] = "production"
    if args.host:
        updates["DEMO_HOST"] = args.host
        updates["PUBLIC_ORIGIN"] = "https://" + args.host
    path.write_text(update_assignments(path.read_text(encoding="utf-8-sig"), updates), encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
    print("Demo access configured. Restart the API to load it.")
    print("Username:", updates["DEMO_USERNAME"])
    if generated:
        print("New password:", password)
    else:
        print("Existing password preserved; inspect your local .env if needed.")
    print("Share demo credentials privately with reviewers; never commit .env.")


if __name__ == "__main__":
    main()
