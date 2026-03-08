#!/bin/bash
PROMPT='/ralph:loop "Read the plan file at /abs/path/IMPLEMENTATION_PLAN.md. Review the overall progress to understand what has already been done, then continue from where the plan was left off by finding the first unchecked checkpoint (### [ ]). Read the context, scope, and steps for that checkpoint. Execute the work. Run the required verification commands. If verification passes, modify /abs/path/IMPLEMENTATION_PLAN.md to change that specific '\''### [ ]'\'' to '\''### [x]'\''. Create a git commit. If there are no unchecked checkpoints remaining in the file, output exactly <promise>PLAN_COMPLETE</promise>." --completion-promise "PLAN_COMPLETE" --max-iterations 20'

CURRENT_PROMPT="$PROMPT"

# This is what setup.sh produces for original prompt:
ORIGINAL_PROMPT='Read the plan file at /abs/path/IMPLEMENTATION_PLAN.md. Review the overall progress to understand what has already been done, then continue from where the plan was left off by finding the first unchecked checkpoint (### [ ]). Read the context, scope, and steps for that checkpoint. Execute the work. Run the required verification commands. If verification passes, modify /abs/path/IMPLEMENTATION_PLAN.md to change that specific '\''### [ ]'\'' to '\''### [x]'\''. Create a git commit. If there are no unchecked checkpoints remaining in the file, output exactly <promise>PLAN_COMPLETE</promise>.'

CLEAN_CURRENT=$(echo "$CURRENT_PROMPT" | sed -E 's/^\/ralph:loop[[:space:]]+//' | sed -E 's/--max-iterations[[:space:]]+[^[:space:]]+[[:space:]]*//' | sed -E 's/--completion-promise[[:space:]]+[^[:space:]]+[[:space:]]*//' | xargs)
CLEAN_ORIGINAL=$(echo "$ORIGINAL_PROMPT" | xargs)

if [[ "$CLEAN_CURRENT" != "$CLEAN_ORIGINAL" ]]; then
    echo "Mismatch!"
    echo "CLEAN_CURRENT:  $CLEAN_CURRENT"
    echo "CLEAN_ORIGINAL: $CLEAN_ORIGINAL"
else
    echo "Match!"
fi
