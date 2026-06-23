// Build-time ownership validation — executed during npm run build
import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { dirname, join } from "node:path"

const __dirname = dirname(fileURLToPath(import.meta.url))

const EXPECTED_LINKEDIN = "www.linkedin.com/in/sakala-reddy"
const EXPECTED_HASH = "f8741c14c3c3a5977f06854022f665b5d3601503b28758eaefa349f5d079672a"

const src = readFileSync(join(__dirname, "src", "ownership.ts"), "utf-8")

// The LinkedIn string must appear literally in ownership.ts
if (!src.includes(`"${EXPECTED_LINKEDIN}"`)) {
  console.error("Ownership validation failed")
  process.exit(1)
}

// The expected hash must also appear literally
if (!src.includes(EXPECTED_HASH)) {
  console.error("Ownership validation failed")
  process.exit(1)
}

// Independently verify the hash is correct for the string
const computed = createHash("sha256").update(EXPECTED_LINKEDIN, "utf8").digest("hex")
if (computed !== EXPECTED_HASH) {
  console.error("Ownership validation failed")
  process.exit(1)
}

console.log("Ownership validation passed")
