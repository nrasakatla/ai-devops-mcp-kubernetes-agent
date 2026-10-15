#!/usr/bin/env bash
# Secret / sensitive-data scan for the repository.
#
# Uses gitleaks if available, else a comprehensive grep-based sweep. Exits
# non-zero if any high-confidence secret pattern is found in tracked files.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

echo "[*] Scanning repository at ${ROOT}"
echo

found=0

if command -v gitleaks >/dev/null 2>&1; then
  echo "[*] Running gitleaks ..."
  if gitleaks detect --source "${ROOT}" --no-git --report-format json \
      --report-path /tmp/ai-devops-gitleaks.json >/dev/null 2>&1; then
    echo "[*] gitleaks: no leaks found"
  else
    echo "[!] gitleaks detected potential leaks:"
    cat /tmp/ai-devops-gitleaks.json 2>/dev/null
    found=1
  fi
  echo
fi

echo "[*] Running grep-based sweeps (tracked files only) ..."

# Only scan files that would be committed (respect .gitignore via git ls-files
# when in a repo; otherwise fall back to find excluding vendored dirs).
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  FILES="$(git ls-files)"
else
  FILES="$(find . -type f -not -path './.git/*' -not -path './.venv/*' -not -path './node_modules/*')"
fi

# High-confidence AWS access key pattern (AKIA...)
for f in ${FILES}; do
  if grep -HnE 'AKIA[0-9A-Z]{16}' "$f" >/dev/null 2>&1; then
    echo "[!] AWS access key id found in: $f"
    grep -HnE 'AKIA[0-9A-Z]{16}' "$f"
    found=1
  fi
  # Private key material — match the BEGIN/END marker without embedding the
  # full literal in a way that makes this script self-match. The regex here
  # still catches real PEM headers in other files.
  if grep -HnE 'BEGIN [A-Z ]*PRIVATE KEY' "$f" >/dev/null 2>&1; then
    echo "[!] Private key material found in: $f"
    found=1
  fi
  # Private IP ranges (we must not leak any real infra)
  if grep -HnE '(172\.(1[6-9]|2[0-9]|3[0-1])\.|10\.[0-9]{1,3}\.|192\.168\.)' "$f" >/dev/null 2>&1; then
    echo "[!] Private IP address found in: $f"
    grep -HnE '(172\.(1[6-9]|2[0-9]|3[0-1])\.|10\.[0-9]{1,3}\.|192\.168\.)' "$f"
    found=1
  fi
done

echo
if [[ "${found}" -eq 1 ]]; then
  echo "[!] SCAN FAILED: sensitive patterns detected. Review before publishing."
  exit 1
else
  echo "[*] SCAN PASSED: no secrets, private IPs, or key material detected."
fi
