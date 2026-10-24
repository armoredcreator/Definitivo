from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REMOTE_URL = "https://github.com/armoredcreator/Definitivo.git"
BRANCH = "main"
FORBIDDEN_PREFIXES = (
    "credentials/",
    "storage/",
    "runtime/models/",
    "runtime/telegram-bot-api/",
    "armoredspeech/runtime/",
    "armoredstudio/runtime/",
)
FORBIDDEN_SUFFIXES = (
    ".session",
    ".session-journal",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".exe",
    ".dll",
    ".pth",
)
FORBIDDEN_PATHS = {"armoredspeech/assets/efeitosonoro.wav"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_private_path(path: str) -> bool:
    normalized = path.replace("\\", "/").casefold()
    return (
        normalized.startswith(tuple(prefix.casefold() for prefix in FORBIDDEN_PREFIXES))
        or normalized in FORBIDDEN_PATHS
        or normalized.endswith(FORBIDDEN_SUFFIXES)
        or (normalized.startswith(".env") and normalized != ".env.example")
    )


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45,
    )
    return result.stdout.strip()


def create_manifest() -> tuple[dict[str, object], list[str]]:
    errors: list[str] = []
    try:
        paths = [value for value in git("ls-files", "-z").split("\0") if value]
        commit = git("rev-parse", "HEAD")
        branch = git("branch", "--show-current")
        remote_url = git("remote", "get-url", "origin")
        remote_state = git("ls-remote", "origin", f"refs/heads/{BRANCH}")
        remote_commit = remote_state.split()[0] if remote_state else ""
        changes = git("status", "--porcelain", "--untracked-files=all")
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return {}, [f"Git não pôde confirmar o estado do projeto: {exc}"]

    files: list[dict[str, object]] = []
    for relative in paths:
        if is_private_path(relative):
            errors.append(f"Arquivo privado está marcado para versionamento: {relative}")
            continue
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"Arquivo versionado ausente: {relative}")
            continue
        files.append(
            {
                "path": relative.replace("\\", "/"),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    if sys.version_info[:3] != (3, 11, 9):
        errors.append(f"Python 3.11.9 exigido; encontrado {sys.version.split()[0]}")
    if branch != BRANCH:
        errors.append(f"Branch esperada: {BRANCH}; branch atual: {branch or '(detached)'}")
    if remote_url.rstrip("/") != REMOTE_URL:
        errors.append("A origem Git não corresponde ao repositório oficial Definitivo")
    if not remote_commit or remote_commit != commit:
        errors.append("O commit local não corresponde ao main publicado no GitHub")
    if changes:
        errors.append("A árvore Git possui alterações locais ou arquivos não versionados")
    if not files:
        errors.append("Nenhum arquivo versionado foi incluído no manifesto")

    manifest: dict[str, object] = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": REMOTE_URL,
        "branch": branch,
        "commit": commit,
        "remote_commit": remote_commit,
        "worktree_clean": not changes,
        "tracked_file_count": len(files),
        "files": files,
    }
    return manifest, errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Confere a sincronização do Definitivo e grava hashes dos arquivos versionados."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "storage" / "validation" / "source-integrity.json",
        help="Destino do manifesto local (padrão: storage/validation/source-integrity.json).",
    )
    args = parser.parse_args()

    manifest, errors = create_manifest()
    if manifest:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output = output.resolve()
        if not output.is_relative_to((ROOT / "storage" / "validation").resolve()):
            errors.append("O manifesto só pode ser salvo em storage/validation/")
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"MANIFEST={output}")
            print(f"COMMIT={manifest['commit']}")
            print(f"TRACKED_FILES={manifest['tracked_file_count']}")

    for error in errors:
        print(f"ERROR={error}", file=sys.stderr)
    if errors:
        return 1
    print("INSTALLATION_INTEGRITY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
