"""Put scripts/ on the import path, so the tests import the engine the way the piece scripts do."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
