"""
Owner-only release signing tool.

Run ONCE to generate a key pair and sign all protected files:
    python sign_release.py --init          # generate key pair + sign
    python sign_release.py --sign          # re-sign after code changes

The private key is saved to ownership.key (gitignored — never commit it).
The public key and signature are embedded in ownership.py automatically.

Without ownership.key, nobody can produce a valid signature for
any modified version of the protected files.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Files whose SHA-256 are included in the signed manifest.
# ownership.py itself is NOT listed — it holds the signature, so including
# it would create a circular dependency.
PROTECTED = [
    "main.py",
    "db.py",
    "ai_analyzer.py",
    "validate_ownership.py",
]

PRIVATE_KEY_FILE = os.path.join(HERE, "ownership.key")
OWNERSHIP_FILE   = os.path.join(HERE, "ownership.py")


def _require_cryptography():
    try:
        from cryptography.hazmat.primitives.asymmetric.ec import (
            ECDSA, generate_private_key, SECP256R1,
        )
        from cryptography.hazmat.primitives import hashes, serialization
        return True
    except ImportError:
        print("ERROR: install the 'cryptography' package first:", file=sys.stderr)
        print("  pip install cryptography", file=sys.stderr)
        sys.exit(1)


def build_manifest():
    """Return canonical JSON manifest: {filename: sha256hex, ...}."""
    entries = {}
    for name in sorted(PROTECTED):
        path = os.path.join(HERE, name)
        with open(path, "rb") as f:
            entries[name] = hashlib.sha256(f.read()).hexdigest()
    return json.dumps(entries, sort_keys=True).encode("utf-8")


def generate_keys():
    from cryptography.hazmat.primitives.asymmetric.ec import generate_private_key, SECP256R1
    from cryptography.hazmat.primitives import serialization

    priv = generate_private_key(SECP256R1())
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return priv_pem, pub_pem


def sign_manifest(priv_pem: str, manifest: bytes) -> str:
    from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
    from cryptography.hazmat.primitives import hashes, serialization

    priv = serialization.load_pem_private_key(priv_pem.encode(), password=None)
    sig_bytes = priv.sign(manifest, ECDSA(hashes.SHA256()))
    return base64.b64encode(sig_bytes).decode()


def embed_into_ownership(pub_pem: str, sig_b64: str):
    """Patch _OWNER_PUBLIC_KEY and _OWNER_SIG in ownership.py."""
    with open(OWNERSHIP_FILE, "r", encoding="utf-8") as f:
        src = f.read()

    key_block = f'_OWNER_PUBLIC_KEY = """{pub_pem}"""'
    sig_block  = f'_OWNER_SIG = "{sig_b64}"'

    if "_OWNER_PUBLIC_KEY" in src:
        src = re.sub(r'_OWNER_PUBLIC_KEY\s*=\s*(?:""".*?"""|"[^"]*")', key_block, src, flags=re.DOTALL)
    else:
        src = src.replace(
            "def validate_ownership()",
            f"{key_block}\n{sig_block}\n\ndef validate_ownership()",
        )

    if "_OWNER_SIG" in src:
        src = re.sub(r'_OWNER_SIG\s*=\s*"[^"]*"', sig_block, src)

    with open(OWNERSHIP_FILE, "w", encoding="utf-8") as f:
        f.write(src)

    print(f"  Embedded public key and signature into {OWNERSHIP_FILE}")


def embed_fingerprint(pub_pem: str):
    """Embed public key fingerprint and identity hash into every signed file.
    The plaintext ownership identifier is NEVER embedded — only its SHA-256 hash."""
    fp = hashlib.sha256(pub_pem.encode("utf-8")).hexdigest()
    # Identity hash = SHA-256 of the ownership URL (computed from ownership.py constants)
    import re as _re
    src = open(os.path.join(HERE, "ownership.py"), encoding="utf-8").read()
    eh_m = _re.search(r'_EXPECTED_HASH\s*=\s*"([a-f0-9]{64})"', src)
    identity_hash = eh_m.group(1) if eh_m else ""

    # validate_ownership.py: update OWNER_KEY_FINGERPRINT
    _embed_fp_in_file(
        os.path.join(HERE, "validate_ownership.py"),
        r'OWNER_KEY_FINGERPRINT\s*=\s*"[^"]*"',
        f'OWNER_KEY_FINGERPRINT = "{fp}"',
    )

    # main.py, db.py, ai_analyzer.py: embed key fingerprint + identity hash (no plaintext URL)
    for fname in ("main.py", "db.py", "ai_analyzer.py"):
        fpath = os.path.join(HERE, fname)
        _embed_fp_in_file(
            fpath,
            r'_OWNER_KEY_FINGERPRINT\s*=\s*"[^"]*"',
            f'_OWNER_KEY_FINGERPRINT = "{fp}"',
            fallback_after=r'import ownership[^\n]*\n',
        )
        if identity_hash:
            _embed_fp_in_file(
                fpath,
                r'_OWNER_LINKEDIN_HASH\s*=\s*"[^"]*"',
                f'_OWNER_LINKEDIN_HASH = "{identity_hash}"',
                fallback_after=r'_OWNER_KEY_FINGERPRINT\s*=\s*"[^"]*"\n',
            )
        # Remove old plaintext _OWNER_LINKEDIN if present
        with open(fpath, "r", encoding="utf-8") as fh:
            content = fh.read()
        cleaned = _re.sub(r'\n_OWNER_LINKEDIN\s*=\s*"[^"]*"', '', content)
        if cleaned != content:
            with open(fpath, "w", encoding="utf-8") as fh:
                fh.write(cleaned)

    print(f"  Embedded key fingerprint ({fp[:16]}...) and identity hash into all signed files")


def _embed_fp_in_file(fpath: str, pattern: str, replacement: str, fallback_after: str = None):
    with open(fpath, "r", encoding="utf-8") as f:
        src = f.read()

    if re.search(pattern, src):
        src = re.sub(pattern, replacement, src)
    elif fallback_after:
        m = re.search(fallback_after, src)
        if m:
            src = src[: m.end()] + replacement + "\n" + src[m.end() :]
        else:
            src += f"\n{replacement}\n"
    else:
        src += f"\n{replacement}\n"

    with open(fpath, "w", encoding="utf-8") as f:
        f.write(src)


def cmd_init():
    _require_cryptography()

    if os.path.exists(PRIVATE_KEY_FILE):
        print(f"Private key already exists at {PRIVATE_KEY_FILE}")
        print("Use --sign to re-sign without regenerating the key pair.")
        sys.exit(1)

    print("Generating ECDSA P-256 key pair...")
    priv_pem, pub_pem = generate_keys()

    with open(PRIVATE_KEY_FILE, "w") as f:
        f.write(priv_pem)
    os.chmod(PRIVATE_KEY_FILE, 0o600)
    print(f"  Private key saved to: {PRIVATE_KEY_FILE}  (NEVER commit this file)")

    embed_fingerprint(pub_pem)
    manifest = build_manifest()
    sig_b64 = sign_manifest(priv_pem, manifest)
    print(f"  Signed manifest: {manifest[:80].decode()}...")
    embed_into_ownership(pub_pem, sig_b64)
    print("Done. Add ownership.key to .gitignore and keep it secret.")


def cmd_sign():
    _require_cryptography()

    if not os.path.exists(PRIVATE_KEY_FILE):
        print(f"ERROR: private key not found at {PRIVATE_KEY_FILE}", file=sys.stderr)
        print("Run --init first, or restore your ownership.key from a secure backup.")
        sys.exit(1)

    with open(PRIVATE_KEY_FILE, "r") as f:
        priv_pem = f.read()

    # Re-read public key from private key
    from cryptography.hazmat.primitives import hashes, serialization
    priv = serialization.load_pem_private_key(priv_pem.encode(), password=None)
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    embed_fingerprint(pub_pem)
    manifest = build_manifest()
    sig_b64 = sign_manifest(priv_pem, manifest)
    print(f"  Signed manifest: {manifest[:80].decode()}...")
    embed_into_ownership(pub_pem, sig_b64)
    print("Done. Rebuild the Docker image to apply.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Owner-only release signing tool")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--init", action="store_true", help="Generate key pair and sign")
    grp.add_argument("--sign", action="store_true", help="Re-sign with existing key")
    args = parser.parse_args()

    if args.init:
        cmd_init()
    elif args.sign:
        cmd_sign()
