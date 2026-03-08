#!/bin/bash
arg1='"Read the plan file at /Users/evren/code/r2t4/scene-analyser/plans/Config-Driven Pipelined Scene Analysis.md. Review the overall progress" --completion-promise "PLAN_COMPLETE" --max-iterations 20'

if [[ 1 -eq 1 ]]; then
  if [[ "$arg1" =~ ^- ]] || [[ "$arg1" =~ " --" ]]; then
     eval set -- "$arg1"
  fi
fi

MAX_ITERATIONS=5
COMPLETION_PROMISE=""
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

echo "PROMPT='$PROMPT'"
echo "MAX='$MAX_ITERATIONS'"
echo "PROMISE='$COMPLETION_PROMISE'"
