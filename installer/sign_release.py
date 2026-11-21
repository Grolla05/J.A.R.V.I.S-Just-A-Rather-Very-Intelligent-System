"""Assina o instalador com Minisign (Ed25519) — usado pelo release.yml.

    # uma vez, na máquina do mantenedor (a chave secreta vai para um arquivo):
    python installer/sign_release.py --generate C:\\caminho\\fora\\do\\repo\\jarvis-release.key
    #   → cole a chave pública impressa em backend/core/updater.py (PUBLIC_KEY)
    #   → gh secret set MINISIGN_SECRET_KEY --env release < C:\\...\\jarvis-release.key

    # no CI (chave secreta na variável de ambiente MINISIGN_SECRET_KEY):
    python installer/sign_release.py dist/JARVIS-Setup.exe --version 1.2.3
    #   → dist/JARVIS-Setup.exe.minisig (e confere contra a PUBLIC_KEY embutida)

Nunca imprime nem grava a chave secreta no log.
"""
import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "backend" / "core"


def _load(name):
    """Carrega backend/core/<name>.py sozinho (sem rodar o pacote core)."""
    spec = importlib.util.spec_from_file_location(f"jarvis_{name}", CORE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def embedded_public_key():
    text = (CORE / "updater.py").read_text(encoding="utf-8")
    match = re.search(r'^PUBLIC_KEY = "([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("PUBLIC_KEY não encontrada em backend/core/updater.py")
    return match.group(1)


def generate(dest):
    minisign = _load("minisign")
    dest = Path(dest)
    if dest.exists():
        raise SystemExit(f"{dest} já existe: não sobrescrevo uma chave.")
    if ROOT in dest.resolve().parents:
        raise SystemExit("Guarde a chave secreta FORA do repositório.")
    secret, public = minisign.generate_keypair()
    dest.write_text(secret, encoding="ascii")
    print(f"Chave secreta gravada em {dest} (não versione; vai para o secret MINISIGN_SECRET_KEY).")
    print(f"Chave pública (PUBLIC_KEY em backend/core/updater.py):\n{public}")


def sign(path, version):
    minisign = _load("minisign")
    secret = os.environ.get("MINISIGN_SECRET_KEY", "").strip()
    if not secret:
        raise SystemExit("MINISIGN_SECRET_KEY vazia: configure o secret no environment `release`.")
    path = Path(path)
    trusted = f"file:{path.name}\tversion:{version or '?'}\thashed"
    sig = minisign.sign_file(path, secret, trusted_comment=trusted,
                             untrusted_comment="assinatura do J.A.R.V.I.S (minisign)")
    sig_path = path.with_name(path.name + ".minisig")
    sig_path.write_text(sig, encoding="utf-8", newline="\n")
    # Assinou com a chave que o app instalado vai aceitar? Senão o update quebra.
    minisign.verify_file(path, sig, embedded_public_key())
    print(f"Assinado: {sig_path.name} (conferido com a PUBLIC_KEY embutida)")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", nargs="?", help="arquivo a assinar (ex.: dist/JARVIS-Setup.exe)")
    parser.add_argument("--version", default="", help="versão gravada no trusted comment")
    parser.add_argument("--generate", metavar="ARQUIVO_SECRETO", help="gera um par de chaves novo")
    args = parser.parse_args(argv)
    if args.generate:
        generate(args.generate)
    elif args.file:
        sign(args.file, args.version)
    else:
        parser.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
