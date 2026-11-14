#!/bin/sh
# Runs every proof test and saves the full output (including AUDIT log lines) to tests/logs/.
set -u
cd "$(dirname "$0")/.."
mkdir -p tests/logs
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG="tests/logs/proof_${STAMP}.log"
RC_FILE=$(mktemp)
{ python -m pytest tests -v -s -p no:cacheprovider \
    -o log_cli=true --log-cli-level=INFO \
    --log-cli-format="%(asctime)s %(name)s %(levelname)s %(message)s" \
    --junitxml="tests/logs/junit_${STAMP}.xml"; echo $? > "$RC_FILE"; } 2>&1 | tee "$LOG"
STATUS=$(cat "$RC_FILE")
cp "$LOG" tests/logs/proof_latest.log
echo "Saved log: $LOG (exit $STATUS)"
exit "$STATUS"
