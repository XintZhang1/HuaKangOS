"""Run the bounded external-model form trial; requires explicit private config."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.assistant_simulation import main

if __name__ == '__main__':
    main()
