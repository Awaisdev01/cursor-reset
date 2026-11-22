#!/usr/bin/env bash
# Build cursor-reset.app + .dmg for macOS
set -e
pip3 install --quiet py2app || pip3 install --user --quiet py2app
cat > setup.py << 'PY'
from setuptools import setup
setup(
    app=['gui.py'],
    name='cursor-reset',
    options={'py2app': {'packages': ['tkinter'], 'argv_emulation': False}},
    setup_requires=['py2app'],
)
PY
python3 setup.py py2app -A 2>/dev/null || python3 setup.py py2app
mkdir -p dist/dmg
cp -r dist/cursor-reset.app dist/dmg/
hdiutil create -volname cursor-reset -srcfolder dist/dmg -ov -format UDZO dist/cursor-reset.dmg
echo "✔ dist/cursor-reset.dmg"
