"""configs — one module per merged tool, holding that tool's own domain
constants unchanged (values, not names, kept identical to the source
project). Kept out of the shared root config.py because flattening
collided: GhostTrace's and CFIUS Screener's original configs both define
APP_TITLE and DEMO_BANNER with different values."""
