#!/bin/bash
arg1='"Read the plan file" --completion-promise "PLAN_COMPLETE" --max-iterations 20'
if [[ "$arg1" =~ ^- ]] || [[ "$arg1" =~ " --" ]]; then
   eval set -- "$arg1"
fi
echo "1: $1"
echo "2: $2"
echo "3: $3"
echo "4: $4"
echo "5: $5"
