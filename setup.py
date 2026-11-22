from setuptools import setup
setup(
    app=['gui.py'],
    name='cursor-reset',
    options={'py2app': {'packages': ['tkinter'], 'argv_emulation': False}},
    setup_requires=['py2app'],
)
