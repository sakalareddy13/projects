"""Build-time ownership validation — executed during Docker image build."""
import hashlib
import re
import sys
import os as _os

# Identity anchor hash — SHA-256 of the ownership identifier.
# The plaintext identifier is NEVER stored here; it is XOR-encoded in ownership.py.
# Changing this value breaks the XOR decode in ownership.py → app refuses to start.
EXPECTED_HASH = "f8741c14c3c3a5977f06854022f665b5d3601503b28758eaefa349f5d079672a"

# SHA-256 of _OWNER_PUBLIC_KEY PEM in ownership.py — populated by sign_release.py.
# Changing _OWNER_PUBLIC_KEY without updating this causes a build failure.
# Changing this constant triggers Guard 13 (ECDSA) at runtime.
OWNER_KEY_FINGERPRINT = "02836ac5a83298642e2025fa314e8bca9592dc120dd81215d5874777b41eadd7"

_here = _os.path.dirname(_os.path.abspath(__file__))


def _read(filename):
    with open(_os.path.join(_here, filename), encoding="utf-8") as f:
        return f.read()


def _active(src):
    """Strip comment-only lines so commented-out code doesn't fool checks."""
    return "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))


def _fail(msg):
    print(f"Ownership validation failed: {msg}", file=sys.stderr)
    sys.exit(1)


src = _read("ownership.py")
active_src = _active(src)

# ── Check 1: XOR-encoded identity parts must be present (no plaintext) ───────
# The ownership identifier is stored as XOR-encoded integer tuples (_A1, _A2)
# with key derived from EXPECTED_HASH. Plaintext is never in source.
if "_A1" not in src or "_A2" not in src or "_AK" not in src:
    _fail("XOR-encoded identity parts (_A1/_A2/_AK) missing from ownership.py — identity check disabled")
if "OWNER_LINKEDIN" not in src:
    _fail("OWNER_LINKEDIN assembly missing from ownership.py")

# ── Check 2: expected hash present literally ──────────────────────────────────
if EXPECTED_HASH not in src:
    _fail("Expected hash missing from ownership.py")

# ── Check 3: XOR-decoded identity must match expected hash ───────────────────
# Decode _A1 + _A2 from ownership.py source using EXPECTED_HASH as key
_a1_m = re.search(r'_A1\s*=\s*\(([\d,\s]+)\)', src)
_a2_m = re.search(r'_A2\s*=\s*\(([\d,\s]+)\)', src)
if not _a1_m or not _a2_m:
    _fail("Cannot extract _A1/_A2 from ownership.py for integrity check")
_a1 = tuple(int(x.strip()) for x in _a1_m.group(1).split(',') if x.strip())
_a2 = tuple(int(x.strip()) for x in _a2_m.group(1).split(',') if x.strip())
_ak = bytes.fromhex(EXPECTED_HASH)
_decoded_id = bytes(v ^ k for v, k in zip(_a1 + _a2, _ak)).decode("utf-8", errors="replace")
if hashlib.sha256(_decoded_id.encode()).hexdigest() != EXPECTED_HASH:
    _fail("XOR-decoded identity does not match expected hash — _A1/_A2 encoding has been tampered")

# ── Check 4: validate_ownership() is called (not commented out) ───────────────
if "validate_ownership()" not in active_src:
    _fail("validate_ownership() call removed or commented out in ownership.py")

# ── Check 5: the function BODY contains hash verification (not a no-op) ───────
fn_match = re.search(
    r"def validate_ownership\s*\([^)]*\)\s*(?:->[^:]+)?:(.*?)(?=\ndef |\Z)",
    src,
    re.DOTALL,
)
if not fn_match:
    _fail("validate_ownership function definition not found in ownership.py")
fn_body = fn_match.group(1)
fn_body_active = _active(fn_body)
if "sys.exit" not in fn_body_active and "_fail()" not in fn_body_active and "_FORCE_EXIT" not in fn_body_active:
    _fail("validate_ownership body contains no exit mechanism — function may be no-oped")
if "hashlib.sha256" not in fn_body_active and "hexdigest" not in fn_body_active:
    _fail("validate_ownership body does not contain hash check — function may be no-oped")
if "_A1" not in fn_body_active or "_A2" not in fn_body_active:
    _fail("validate_ownership body does not reference XOR identity parts — identity check may be stripped")

# ── Check 5b: the function BODY contains cryptographic signature verification ─
if "_OWNER_PUBLIC_KEY" not in fn_body_active:
    _fail("validate_ownership body missing _OWNER_PUBLIC_KEY signature verification — function may be no-oped")
if "_OWNER_SIG" not in fn_body_active:
    _fail("validate_ownership body missing _OWNER_SIG signature verification — function may be no-oped")
if "pub.verify" not in fn_body_active and "_pub.verify" not in fn_body_active:
    _fail("validate_ownership body missing pub.verify() call — signature check may be removed")

# ── Check 5c: exit uses _FORCE_EXIT (os._exit) not sys.exit ──────────────────
if "_FORCE_EXIT" not in active_src:
    _fail("ownership.py does not capture _FORCE_EXIT = _os._exit — sys.exit bypass possible")
if "_fail()" not in fn_body_active and "_fail(" not in fn_body_active:
    _fail("validate_ownership body does not call _fail() — exit logic may be stripped")

# ── Check 5d: background watchdog is wired up ────────────────────────────────
if "_background_revalidation" not in active_src:
    _fail("_background_revalidation watchdog missing from ownership.py")
if "_background_revalidation()" not in active_src:
    _fail("_background_revalidation() is not called at module level — watchdog disabled")

# ── Check 10: Dockerfile sets PYTHONDONTWRITEBYTECODE ────────────────────────
dockerfile_src = _read("Dockerfile")
dockerfile_active = _active(dockerfile_src)
if "PYTHONDONTWRITEBYTECODE" not in dockerfile_active:
    _fail("Dockerfile missing PYTHONDONTWRITEBYTECODE=1 — .pyc cache attack possible")

# ── Check 11: Dockerfile runs validate_ownership.py at build time ─────────────
if "validate_ownership.py" not in dockerfile_active:
    _fail("Dockerfile does not run validate_ownership.py — build-time checks skipped")

# ── Check 6: main.py imports ownership ────────────────────────────────────────
main_src = _read("main.py")
main_active = _active(main_src)
if "import ownership" not in main_active:
    _fail("'import ownership' missing from main.py")

# ── Check 7: main.py explicitly calls validate_ownership() in lifespan ────────
if "ownership.validate_ownership()" not in main_active:
    _fail("ownership.validate_ownership() call missing from main.py lifespan")

# ── Check 8: db.py imports ownership ─────────────────────────────────────────
db_src = _read("db.py")
if "import ownership" not in _active(db_src):
    _fail("'import ownership' missing from db.py")

# ── Check 9: ai_analyzer.py imports ownership ────────────────────────────────
ai_src = _read("ai_analyzer.py")
if "import ownership" not in _active(ai_src):
    _fail("'import ownership' missing from ai_analyzer.py")

# ── Check 12: validate_ownership.py must be in _SIGNED_FILES ─────────────────
if '"validate_ownership.py"' not in src and "'validate_ownership.py'" not in src:
    _fail("validate_ownership.py is not in _SIGNED_FILES — it can be silently modified without triggering Guard 13")

# ── Check 13: public key fingerprint in ownership.py must match OWNER_KEY_FINGERPRINT ──
if OWNER_KEY_FINGERPRINT:
    key_match = re.search(r'_OWNER_PUBLIC_KEY\s*=\s*"""(.*?)"""', src, re.DOTALL)
    if not key_match or not key_match.group(1).strip():
        _fail("_OWNER_PUBLIC_KEY is missing or empty in ownership.py — Guards 13/17 are disabled")
    actual_fp = hashlib.sha256(key_match.group(1).encode("utf-8")).hexdigest()
    if actual_fp != OWNER_KEY_FINGERPRINT:
        _fail("_OWNER_PUBLIC_KEY fingerprint mismatch — public key may have been swapped in ownership.py")

# ── Check 14: meta-hash constant is mathematically correct in ownership.py ───
meta_match = re.search(r'_META_HASH\s*=\s*"([a-f0-9]{64})"', src)
if not meta_match:
    _fail("_META_HASH constant missing from ownership.py — Guard 4 is disabled")
expected_meta = hashlib.sha256(EXPECTED_HASH.encode("utf-8")).hexdigest()
if meta_match.group(1) != expected_meta:
    _fail("_META_HASH value is wrong — Guard 4 would always pass regardless of identity hash")

# ── Check 15: watchdog sleep must be ≤ 15 s ──────────────────────────────────
sleep_match = re.search(r'time\.sleep\((\d+)\)', src)
if not sleep_match or int(sleep_match.group(1)) > 15:
    _fail("Watchdog sleep interval is missing or exceeds 15 s — in-place edits may go undetected")

# ── Check 16: Guard 17 (fingerprint check) code present in function body ──────
if "_pub_fp" not in fn_body_active or "Guard 17" not in fn_body:
    _fail("Guard 17 (public key fingerprint check) removed from validate_ownership body")

# ── Check 17: Guard 18 (identity-hash-in-signed-files) present in function body ──
if "Guard 18" not in fn_body:
    _fail("Guard 18 (identity hash in signed files) removed from validate_ownership body")

# ── Check 18: _OWNER_KEY_FINGERPRINT present in every signed source file ──────
for _check_file, _check_src in [("main.py", main_src), ("db.py", db_src), ("ai_analyzer.py", ai_src)]:
    if "_OWNER_KEY_FINGERPRINT" not in _check_src:
        _fail(f"_OWNER_KEY_FINGERPRINT constant missing from {_check_file} — Guard 17 cannot verify key in that file")

# ── Check 19: Identity hash present in every signed source file ───────────────
# Guard 18 checks for EXPECTED_HASH (not plaintext identifier) in signed files
for _check_file, _check_src in [("main.py", main_src), ("db.py", db_src), ("ai_analyzer.py", ai_src)]:
    if EXPECTED_HASH not in _check_src:
        _fail(f"Identity hash missing from {_check_file} — Guard 18 cannot verify attribution in that file")

# ── Check 20: _MIN_SIZES block present — stub-replacement guard is active ─────
if "_MIN_SIZES" not in active_src:
    _fail("_MIN_SIZES constant missing from ownership.py — Guard 8 (minimum file size) is disabled")

# ── Check 21: Anti-trace guard present in function body ──────────────────────
if "gettrace" not in fn_body_active or "Guard 21" not in fn_body:
    _fail("Guard 21 (anti-trace) removed from validate_ownership body")

# ── Check 22: Anti-profile guard present in function body ────────────────────
if "getprofile" not in fn_body_active or "Guard 22" not in fn_body:
    _fail("Guard 22 (anti-profile) removed from validate_ownership body")

# ── Check 23: Forbidden-module guard present ─────────────────────────────────
if "_BLOCKED_MODULES" not in active_src or "Guard 23" not in fn_body:
    _fail("Guard 23 (forbidden-module detection) removed from ownership.py")

print("Ownership validation passed — all 23 guards verified")
