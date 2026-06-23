"""Application ownership validation — DO NOT MODIFY."""
import base64
import hashlib
import json
import os as _os
import sys

# Capture os._exit at module load time — before any monkey-patching
_FORCE_EXIT = _os._exit

# Identity anchor hash (SHA-256 of the ownership identifier)
_EXPECTED_HASH = "f8741c14c3c3a5977f06854022f665b5d3601503b28758eaefa349f5d079672a"

# SHA-256 of _EXPECTED_HASH (meta-hash — detects tampering of the hash constant)
_META_HASH = "48beab35a4298d0234926c58a461f137fdcf893470bb0c83f506b24c7445d24b"

# Ownership identifier — XOR-encoded with key derived from _EXPECTED_HASH.
# Plaintext never appears in source. Changing _EXPECTED_HASH changes the XOR key,
# which decodes _A1+_A2 to garbage — Guard 2 then fails. Cryptographic interlocking.
_A1 = (143, 3, 107, 58, 175, 170, 203, 252, 26, 98, 236, 46, 12, 149, 10, 216)
_A2 = (252, 9, 123, 44, 193, 230, 51, 139, 131, 194, 100, 135, 181, 29, 3, 83)
_AK = bytes.fromhex(_EXPECTED_HASH)
OWNER_LINKEDIN = bytes(v ^ k for v, k in zip(_A1 + _A2, _AK)).decode()

# ECDSA P-256 public key — embedded by sign_release.py
# Matching private key (ownership.key) stays off-repo with the owner.
_OWNER_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE6lF+7hIbARjaOvjH4GL74Z8AlTvC
iQCcZOkqyxBUYsX7vr9hJq55AIrgj5M3ApRXU9sNw+l4Qc3ujzy9aWPAFA==
-----END PUBLIC KEY-----
"""
_OWNER_SIG = "MEUCIGlenKEsfV8gAQC4PrbdNg97uDqh11J2lv85t6mN1Bd8AiEAyP6AA/vflqUNGcb7UdqqCwuvU0CxYd+s6W8ojlrYCk8="

# Files covered by the cryptographic manifest signature
_SIGNED_FILES = ["ai_analyzer.py", "db.py", "main.py", "validate_ownership.py"]

# Minimum file sizes — prevents stub/empty replacement of signed files
_MIN_SIZES = {
    "ai_analyzer.py": 50000,
    "db.py": 10000,
    "main.py": 50000,
    "validate_ownership.py": 5000,
}

# Analysis tools whose presence signals a bypass attempt
_BLOCKED_MODULES = frozenset({"pdb", "pydevd", "debugpy", "ipdb", "pudb", "birdseye"})

# Watchdog thread reference — checked alive in Guard 20
_watchdog_thread = None


def _fail() -> None:
    print("Ownership validation failed", file=sys.stderr)
    _FORCE_EXIT(1)  # OS-level exit — uncatchable by any Python try/except


def validate_ownership() -> None:
    """Validate application ownership. Exits at OS level if tampered."""

    # ── Guard 1: Core files must exist (PYTHONPATH substitution) ─────────────
    _our_dir = _os.path.dirname(_os.path.abspath(__file__))
    for _f in ("main.py", "db.py", "ai_analyzer.py", "validate_ownership.py"):
        if not _os.path.isfile(_os.path.join(_our_dir, _f)):
            _fail()

    # ── Guard 2: Identity hash integrity ─────────────────────────────────────
    if hashlib.sha256(OWNER_LINKEDIN.encode("utf-8")).hexdigest() != _EXPECTED_HASH:
        _fail()

    # ── Guard 3: Identity self-consistency (computed — no plaintext literal) ──
    _ref = bytes(v ^ k for v, k in zip(_A1 + _A2, bytes.fromhex(_EXPECTED_HASH))).decode()
    if OWNER_LINKEDIN != _ref:
        _fail()

    # ── Guard 4: Meta-hash — SHA-256 of _EXPECTED_HASH itself ────────────────
    if hashlib.sha256(_EXPECTED_HASH.encode("utf-8")).hexdigest() != _META_HASH:
        _fail()

    # ── Guard 5: validate_ownership.py must remain in the signed manifest ─────
    if "validate_ownership.py" not in _SIGNED_FILES:
        _fail()

    # ── Guard 6: _SIGNED_FILES exact set — no additions or removals ───────────
    _expected_set = {"ai_analyzer.py", "db.py", "main.py", "validate_ownership.py"}
    if set(_SIGNED_FILES) != _expected_set or len(_SIGNED_FILES) != 4:
        _fail()

    # ── Guard 7: Signed files must not be symlinks ────────────────────────────
    for _fname in _SIGNED_FILES:
        if _os.path.islink(_os.path.join(_our_dir, _fname)):
            _fail()

    # ── Guard 8: Signed files must exceed minimum byte sizes ─────────────────
    for _fname, _min_sz in _MIN_SIZES.items():
        if _os.path.getsize(_os.path.join(_our_dir, _fname)) < _min_sz:
            _fail()

    # ── Guard 9: _FORCE_EXIT identity — os._exit must not be monkey-patched ──
    if _FORCE_EXIT is not _os._exit:
        _fail()

    # ── Guard 10: hashlib.sha256 integrity — test against known vector ────────
    _hv = "01b8016fdce455c4343951d02b110bd9c02ce8456f43f8893c8b4ccbb1ca54aa"
    if hashlib.sha256(b"ownership").hexdigest() != _hv:
        _fail()

    # ── Guard 11: Module __file__ path integrity ──────────────────────────────
    _self = _os.path.join(_our_dir, "ownership.py")
    if not _os.path.isfile(_self) or _os.path.abspath(__file__) != _os.path.abspath(_self):
        _fail()

    # ── Guard 12: sys.exit must not be monkey-patched ────────────────────────
    if type(sys.exit).__name__ not in ("builtin_function_or_method", "method-wrapper"):
        _fail()

    # ── Guard 13: ECDSA manifest signature — always enforced ─────────────────
    try:
        from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
        from cryptography.hazmat.primitives import hashes, serialization

        if not _OWNER_PUBLIC_KEY or not _OWNER_SIG:
            _fail()

        _manifest_entries = {}
        for _fname in sorted(_SIGNED_FILES):
            _fpath = _os.path.join(_our_dir, _fname)
            with open(_fpath, "rb") as _fh:
                _manifest_entries[_fname] = hashlib.sha256(_fh.read()).hexdigest()

        _manifest_bytes = json.dumps(_manifest_entries, sort_keys=True).encode("utf-8")
        _pub = serialization.load_pem_public_key(_OWNER_PUBLIC_KEY.encode("utf-8"))
        _sig = base64.b64decode(_OWNER_SIG)
        _pub.verify(_sig, _manifest_bytes, ECDSA(hashes.SHA256()))

    except Exception:
        _fail()

    # ── Guard 14: Manifest must cover exactly 4 files ────────────────────────
    if len(_manifest_entries) != 4:
        _fail()

    # ── Guard 15: Public key PEM structure validation ─────────────────────────
    _pk = _OWNER_PUBLIC_KEY.strip()
    if not _pk.startswith("-----BEGIN PUBLIC KEY-----"):
        _fail()
    if not _pk.endswith("-----END PUBLIC KEY-----"):
        _fail()

    # ── Guard 16: _OWNER_SIG minimum byte length (ECDSA-P256 DER ≥ 68 bytes) ─
    try:
        if len(base64.b64decode(_OWNER_SIG)) < 68:
            _fail()
    except Exception:
        _fail()

    # ── Guard 17: Public key fingerprint must appear in every signed file ─────
    _pub_fp = hashlib.sha256(_OWNER_PUBLIC_KEY.encode("utf-8")).hexdigest()
    for _fname in _SIGNED_FILES:
        with open(_os.path.join(_our_dir, _fname), encoding="utf-8") as _fh:
            if _pub_fp not in _fh.read():
                _fail()

    # ── Guard 18: Identity hash must appear in every signed file ─────────────
    # Checks via hash — plaintext ownership identifier never stored in signed files
    for _fname in _SIGNED_FILES:
        with open(_os.path.join(_our_dir, _fname), encoding="utf-8") as _fh:
            if _EXPECTED_HASH not in _fh.read():
                _fail()

    # ── Guard 19: sys.modules['ownership'] must resolve to this file ──────────
    _mod = sys.modules.get("ownership")
    if _mod is not None and hasattr(_mod, "__file__") and _mod.__file__:
        if _os.path.abspath(_mod.__file__) != _os.path.abspath(__file__):
            _fail()

    # ── Guard 20: Watchdog thread must still be alive after first startup ──────
    if _watchdog_thread is not None and not _watchdog_thread.is_alive():
        _fail()

    # ── Guard 21: Trace hook detection — reject if debugger is attached ───────
    if sys.gettrace() is not None:
        _fail()

    # ── Guard 22: Profile hook detection ─────────────────────────────────────
    if sys.getprofile() is not None:
        _fail()

    # ── Guard 23: Forbidden analysis-module detection ─────────────────────────
    if _BLOCKED_MODULES & set(sys.modules.keys()):
        _fail()


def _background_revalidation() -> None:
    """Daemon thread: re-validates every 15 s — catches in-place file modification."""
    import threading
    import time
    global _watchdog_thread

    def _loop():
        while True:
            time.sleep(15)
            try:
                validate_ownership()
            except Exception:
                _fail()

    _watchdog_thread = threading.Thread(target=_loop, daemon=True, name="ownership-watchdog")
    _watchdog_thread.start()


# Validate immediately on import — runs before server accepts any request
validate_ownership()

# Start background watchdog — catches in-place file edits while server runs
_background_revalidation()
