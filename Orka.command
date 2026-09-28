#!/bin/zsh
# Double-click on macOS to open the local Orka chat app.
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print "Orka needs its one-time Python setup. See README.md."
  read "reply?Press Return to close."
  exit 1
fi
.venv/bin/python -m orka.web
