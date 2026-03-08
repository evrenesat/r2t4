#!/bin/bash
arg1='"Read the plan file" --completion-promise "PLAN_COMPLETE" --max-iterations 20'
if [[ "$arg1" =~ ^- ]] || [[ "$arg1" =~ " --" ]]; then
   eval set -- "$arg1"
fi
PROMPT_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --max-iterations)
      MAX_ITERATIONS="$2"
      shift 2
      ;;
    --completion-promise)
      COMPLETION_PROMISE="$2"
      shift 2
      ;;
    *)
      PROMPT_ARGS+=("$1")
      shift
      ;;
  esac
done
PROMPT="${PROMPT_ARGS[*]:-}"
echo "PROMPT: '$PROMPT'"
