#!/usr/bin/env python3
import os
import sys
from pathlib import Path

def setup_environment():
    """Sets up the environment for the script to run correctly."""
    # Ensure current directory is in PYTHONPATH so src modules are found
    repo_root = Path(__file__).parent.absolute()
    src_path = repo_root / "src"
    
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    
    # Check if we are in a virtualenv (optional but helpful)
    if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("Warning: It appears you are not running in a virtual environment.")
        print("Please activate your environment first: pyenv local tidal-env")

def main():
    setup_environment()
    
    from tidal_serato_sync.cli import main as cli_main
    cli_main()

if __name__ == "__main__":
    main()
