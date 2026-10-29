"""Resolved user-local locations preserve established macOS installations."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from agent_librarian.locations import user_data, installation_home, personal_state


class LocationTests(unittest.TestCase):
    def test_macos_keeps_established_user_locations(self):
        with patch('agent_librarian.locations.sys.platform', 'darwin'), patch.dict(os.environ, {}, clear=True), patch.object(Path, 'home', return_value=Path('/synthetic-user')):
            self.assertEqual(installation_home(), Path('/synthetic-user/Library/Application Support/AgentLibrarian/installation'))
            self.assertEqual(personal_state(), Path('/synthetic-user/Library/Application Support/AgentLibrarian/personal-local'))

    def test_unix_resolves_current_user_and_xdg_without_macos_paths(self):
        with patch('agent_librarian.locations.sys.platform', 'linux'), patch.dict(os.environ, {}, clear=True), patch.object(Path, 'home', return_value=Path('/synthetic-user')):
            self.assertEqual(user_data(), Path('/synthetic-user/.local/share/agent-librarian'))
            with patch.dict(os.environ, {'XDG_DATA_HOME': '/synthetic-data'}):
                self.assertEqual(installation_home(), Path('/synthetic-data/agent-librarian/installation'))
                self.assertEqual(personal_state(), Path('/synthetic-data/agent-librarian/personal-local'))

    def test_explicit_environment_targets_override_defaults(self):
        with patch.dict(os.environ, {'AGENT_LIBRARIAN_HOME': '/chosen-installation', 'AGENT_LIBRARIAN_STATE': '/chosen-state'}):
            self.assertEqual(installation_home(), Path('/chosen-installation'))
            self.assertEqual(personal_state(), Path('/chosen-state'))
