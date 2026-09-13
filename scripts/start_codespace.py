"""Start the existing API once; keep logs and data inside the codespace."""
from pathlib import Path
import subprocess
import sys
import urllib.request

root = Path(__file__).resolve().parent.parent
try:
    with urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2) as response:
        if response.status == 200:
            print('JobFlow ya está disponible en Ports → 8000.')
            raise SystemExit(0)
except OSError:
    pass
(root / 'data').mkdir(exist_ok=True)
with (root / 'data' / 'server.log').open('ab') as log:
    subprocess.Popen([sys.executable, '-m', 'uvicorn', 'jobflow.main:app', '--host', '0.0.0.0', '--port', '8000'],
                     cwd=root, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     start_new_session=True)
print('JobFlow iniciándose. Abre Ports → 8000 y conserva visibilidad Private.')
