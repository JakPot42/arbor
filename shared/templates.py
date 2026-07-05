"""shared/templates.py — ONE Jinja2Templates instance for the whole app.

Fixes the template-path conflict found during the architecture review:
GhostTrace resolved templates relative to the CWD (`directory="templates"`
— breaks if the process isn't launched from that exact directory),
CFIUS resolved them robustly (`directory=_HERE / "templates"`), DIB
Monitor used a fragile `str(__file__).replace("main.py", "templates")`
string-surgery hack. This adopts CFIUS's already-correct pattern —
anchored to this file's location, not the process's working directory —
as the one implementation everything else uses.

Each tool's templates live in their own subdirectory
(templates/ghosttrace/, templates/cfius/, templates/dib/) so
`templates.TemplateResponse(request, "cfius/result.html", ctx)` is
unambiguous even though multiple tools have a template literally named
`index.html`.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

_HERE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=_HERE / "templates")
