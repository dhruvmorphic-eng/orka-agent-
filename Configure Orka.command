#!/bin/zsh
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print "Orka needs its one-time Python setup. See README.md."
else
  .venv/bin/python -m orka.setup
fi
read "reply?Press Return to close."
