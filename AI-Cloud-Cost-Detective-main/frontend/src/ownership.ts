// Application ownership validation — DO NOT MODIFY

// Ownership identifier — locked to this application
export const OWNER_LINKEDIN = "www.linkedin.com/in/sakala-reddy"

// SHA-256 of the exact OWNER_LINKEDIN string above
const EXPECTED_HASH = "f8741c14c3c3a5977f06854022f665b5d3601503b28758eaefa349f5d079672a"

async function sha256hex(str: string): Promise<string> {
  if (typeof crypto?.subtle?.digest !== "function") {
    // crypto.subtle is unavailable in non-secure (plain HTTP) contexts in some browsers.
    // Treat this as a validation failure so the app doesn't silently start unverified.
    showOwnershipFailure()
    throw new Error("Ownership validation failed")
  }
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str))
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("")
}

function showOwnershipFailure(): void {
  document.body.style.cssText = [
    "margin:0",
    "background:#0f0f0f",
    "color:#fff",
    "font-family:monospace",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "min-height:100vh",
  ].join(";")
  document.body.innerHTML = `
    <div style="text-align:center;padding:2rem;">
      <h1 style="color:#ff4444;font-size:2rem;margin:0 0 1rem;">Ownership validation failed</h1>
      <p style="color:#888;font-size:0.9rem;">This application is owned by</p>
      <p style="color:#aaa;font-size:1rem;margin-top:0.5rem;">www.linkedin.com/in/sakala-reddy</p>
    </div>`
}

/**
 * Validates the LinkedIn ownership constant against its embedded SHA-256 hash.
 * Must be called before the app renders. Halts rendering if tampered.
 */
export async function validateOwnership(): Promise<void> {
  const computed = await sha256hex(OWNER_LINKEDIN)
  if (
    OWNER_LINKEDIN !== "www.linkedin.com/in/sakala-reddy" ||
    computed !== EXPECTED_HASH
  ) {
    showOwnershipFailure()
    throw new Error("Ownership validation failed")
  }
}
