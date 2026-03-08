#!/bin/bash
arg1='"Read the plan file... '\''### [ ]'\'' ..."'
echo "arg1 is: $arg1"
eval set -- "$arg1"
echo "eval result: $1"
