"""Resolve user-local locations; retain the established macOS defaults."""
import os
from pathlib import Path
import sys


def user_data():
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/AgentLibrarian'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'agent-librarian'


def installation_home():
    return Path(os.environ.get('AGENT_LIBRARIAN_HOME', user_data() / 'installation')).expanduser()


def personal_state():
    return Path(os.environ.get('AGENT_LIBRARIAN_STATE', user_data() / 'personal-local')).expanduser()
