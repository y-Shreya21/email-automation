#!/usr/bin/env bash
# ==============================================================================
# Security & Secret Leak Pre-Commit Hook
# Automatically blocks commits containing credentials, tokens, or private data.
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🛡️ Running pre-commit security and leak check...${NC}"

# 1. Check for forbidden staged filenames
FORBIDDEN_PATTERNS=(
    "credentials.json"
    "token.json"
    "client_secret_"
    ".env"
    "outreach_history.db"
    "quarantined_records.xlsx"
    "cleaned_contacts.xlsx"
    "Untitled spreadsheet"
    ".pem"
    ".key"
    ".pdf"
    "preview_dashboard.html"
)

STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM)

if [ -z "$STAGED_FILES" ]; then
    echo -e "${GREEN}✓ No staged files to check.${NC}"
    exit 0
fi

LEAK_DETECTED=0

for file in $STAGED_FILES; do
    for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
        # Whitelist .env.example template
        if [[ "$pattern" == ".env" && "$file" == *".env.example"* ]]; then
            continue
        fi
        if [[ "$file" == *"$pattern"* ]]; then
            echo -e "${RED}❌ COMMIT BLOCKED: Sensitive file staged:${NC} $file"
            echo -e "${YELLOW}   Run: git reset HEAD '$file' to unstage it.${NC}"
            LEAK_DETECTED=1
        fi
    done

    # Block any raw recruiter Excel/CSV spreadsheets except the sanitized synthetic sample
    if [[ "$file" =~ \.(xlsx|xls|csv)$ ]] && [[ "$file" != "sample_recruiter_contacts.xlsx" ]]; then
        echo -e "${RED}❌ COMMIT BLOCKED: Spreadsheets containing contact data cannot be committed:${NC} $file"
        echo -e "${YELLOW}   Run: git reset HEAD '$file'${NC}"
        LEAK_DETECTED=1
    fi
done

# 2. Check staged diffs for high-entropy secret patterns
SUSPICIOUS_DIFF=$(git diff --cached -U0 | grep -E "^\+" | grep -E "(GOCSPX-[A-Za-z0-9_-]{20,}|ya29\.[A-Za-z0-9_-]{20,}|BEGIN (RSA )?PRIVATE KEY|\"client_secret\":\s*\"[^\"]{10,}\"|\"refresh_token\":\s*\"[^\"]{10,}\")" || true)

if [ -n "$SUSPICIOUS_DIFF" ]; then
    echo -e "${RED}❌ COMMIT BLOCKED: Potential secret / credential detected in staged code diff!${NC}"
    echo -e "${YELLOW}   Snippet:${NC}"
    echo "$SUSPICIOUS_DIFF" | head -n 5
    LEAK_DETECTED=1
fi

if [ $LEAK_DETECTED -ne 0 ]; then
    echo -e "\n${RED}🛑 Commit aborted to protect your credentials and data privacy.${NC}\n"
    exit 1
fi

echo -e "${GREEN}✓ Pre-commit security check passed: No secret leaks detected.${NC}"
exit 0
