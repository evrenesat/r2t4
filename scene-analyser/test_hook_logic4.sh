#!/bin/bash
CURRENT_PROMPT='/ralph:loop "Read the plan file" --completion-promise "PLAN_COMPLETE" --max-iterations 20'
ORIGINAL_PROMPT='Read the plan file'

CLEAN_CURRENT=$(echo "$CURRENT_PROMPT" | sed -E 's/^\/ralph:loop[[:space:]]+//' | sed -E 's/--max-iterations[[:space:]]+[^[:space:]]+[[:space:]]*//' | sed -E 's/--completion-promise[[:space:]]+[^[:space:]]+[[:space:]]*//' | xargs)
CLEAN_ORIGINAL=$(echo "$ORIGINAL_PROMPT" | xargs)

echo "CLEAN_CURRENT: '$CLEAN_CURRENT'"
echo "CLEAN_ORIGINAL: '$CLEAN_ORIGINAL'"

if [[ "$CLEAN_CURRENT" != "$CLEAN_ORIGINAL" ]]; then
    echo "Mismatch!"
else
    echo "Match!"
fi
