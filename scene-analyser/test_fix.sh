#!/bin/bash
CURRENT_PROMPT='/ralph:loop "Read the plan file... '\''### [ ]'\'' ..."'
ORIGINAL_PROMPT='Read the plan file... '\''### [ ]'\'' ...'

# Proposed fix: Strip outer quotes first, so xargs behaves the same for both
CLEAN_CURRENT=$(echo "$CURRENT_PROMPT" | sed -E 's/^\/ralph:loop[[:space:]]+//' | sed -E 's/--max-iterations[[:space:]]+[^[:space:]]+[[:space:]]*//' | sed -E 's/--completion-promise[[:space:]]+[^[:space:]]+[[:space:]]*//' | sed -E 's/^"//' | sed -E 's/"$//' | xargs)
CLEAN_ORIGINAL=$(echo "$ORIGINAL_PROMPT" | xargs)

echo "CLEAN_CURRENT:  $CLEAN_CURRENT"
echo "CLEAN_ORIGINAL: $CLEAN_ORIGINAL"

if [[ "$CLEAN_CURRENT" != "$CLEAN_ORIGINAL" ]]; then
    echo "Mismatch!"
else
    echo "Match!"
fi
