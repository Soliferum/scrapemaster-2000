#!/usr/bin/env bash
# ---------------------------------------------------------------
#  Builds the ScrapeMaster2000 app for Mac or Linux.
#  Run in Terminal:   bash build_mac_linux.sh
#  Needs Python 3.8+ (Mac: https://www.python.org/downloads/)
# ---------------------------------------------------------------
set -e
cd "$(dirname "$0")"

PY=python3
command -v $PY >/dev/null || { echo "Python 3 not found - install it from https://www.python.org/downloads/"; exit 1; }

# Build in a private environment so nothing on your system is changed
$PY -m venv .build-env
source .build-env/bin/activate
python -m pip install --upgrade --quiet pip pyinstaller certifi pillow

python -m PyInstaller --noconfirm --clean scrapemaster2000.spec
deactivate

echo
echo "Done! Your app is here: dist/ScrapeMaster2000"
echo "Send that single file to anyone on the same kind of computer - they don't need Python."
