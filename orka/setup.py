"""User-operated credential entry; never accept secrets as command arguments."""
import getpass
import sys

from .settings import save_credentials


def main():
    print("\nORKA / CONNECT AI\n")
    print("In Railway, open Cnvrted's backend service → Variables.")
    print("Copy ANTHROPIC_API_KEY, then paste it below. Input stays hidden.")
    print("It is saved locally in gitignored data/credentials.json with owner-only permissions.")
    print("This is a local plaintext credential file, not encrypted storage. Railway is unchanged.\n")
    if not sys.stdin.isatty():
        print("Open this setup in Terminal. Redirected input is not supported.")
        return 1
    try:
        key = getpass.getpass("Anthropic API key (hidden): ").strip()
        if not key or any(c.isspace() for c in key):
            print("No valid key entered. Nothing saved.")
            return 1
        model = input("Model [claude-sonnet-4-6]: ").strip() or "claude-sonnet-4-6"
        if not model.startswith("claude-") or any(c.isspace() for c in model):
            print("Enter a Claude model ID available to your account. Nothing saved.")
            return 1
        save_credentials(key, model)
        print("\nAI settings saved. Open Orka.command to start.")
        print("Credentials have not been tested. Your first AI request contacts Anthropic and may incur usage charges.")
        return 0
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. Nothing saved.")
        return 1
    except OSError:
        print("Could not save settings. Check local folder permissions; no secret has been printed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
