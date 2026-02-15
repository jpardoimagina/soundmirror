# Setup Guide

This project requires Python 3.11.9 and uses `pyenv` and `pyenv-virtualenv` for environment management.

## Prerequisites

- `pyenv` installed.
- `pyenv-virtualenv` plugin installed.

## Environment Setup

1. **Install the required Python version**:
   ```bash
   pyenv install 3.11.9
   ```

2. **Create the virtual environment**:
   ```bash
   pyenv virtualenv 3.11.9 tidal-env
   ```

3. **Activate the environment**:
   ```bash
   pyenv local tidal-env
   ```

4. **Install dependencies**:
   ```bash
   pip install -e .
   ```
   *(Or simply `pip install tidalapi python-dotenv` if not installing in editable mode)*
