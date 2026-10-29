"""User-local project allowlists. Discovery never creates an allowlist."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
from .gateway.common import Rejected, ident
from .personal.state import private_dir, read_private, write_private

DEFAULT_HOME = Path.home() / 'Library/Application Support/AgentLibrarian/installation'


def project_path(project):
    p = Path(project).expanduser().resolve()
    if not p.is_dir():
        raise Rejected('PROJECT_PATH_INVALID')
    return str(p)


class ProjectMappings:
    def __init__(self, home=DEFAULT_HOME):
        self.home = Path(home).expanduser().absolute()
        self.path = self.home / 'projects.json'

    def load(self):
        if not self.path.exists():
            return {'schema_version': 1, 'projects': {}}
        private_dir(self.home)
        data = read_private(self.path)
        if (not isinstance(data, dict) or set(data) != {'schema_version', 'projects'}
                or data['schema_version'] != 1 or not isinstance(data['projects'], dict)):
            raise Rejected('PROJECT_MAPPING_INVALID')
        for path, mapping in data['projects'].items():
            if not isinstance(path, str) or not Path(path).is_absolute():
                raise Rejected('PROJECT_MAPPING_INVALID')
            if (not isinstance(mapping, dict) or set(mapping) != {'provider', 'notebook_ids'}
                    or mapping['provider'] != 'gemini' or not isinstance(mapping['notebook_ids'], list)
                    or not 1 <= len(mapping['notebook_ids']) <= 20):
                raise Rejected('PROJECT_MAPPING_INVALID')
            for nb in mapping['notebook_ids']:
                ident(nb)
            if len(set(mapping['notebook_ids'])) != len(mapping['notebook_ids']):
                raise Rejected('PROJECT_MAPPING_INVALID')
        return data

    def resolve(self, project):
        path = Path(project_path(project))
        data = self.load()['projects']
        # Nearest explicitly mapped ancestor wins; never use the global pilot selection.
        for candidate in (path, *path.parents):
            if str(candidate) in data:
                return {'status': 'MAPPED', 'project': str(path), 'mapping_project': str(candidate),
                        **data[str(candidate)]}
        return {'status': 'PROJECT_NOT_MAPPED', 'project': str(path), 'notebook_ids': [],
                'action': 'Run librarian setup map --project PROJECT --notebook-id DISCOVERED_ID.'}

    @contextmanager
    def lock(self):
        private_dir(self.home, create=True)
        fd = os.open(self.home / 'projects.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def change(self, project, notebook_ids=None, dry_run=False):
        path = project_path(project)
        if notebook_ids is not None:
            if not 1 <= len(notebook_ids) <= 20:
                raise Rejected('PROJECT_MAPPING_INVALID')
            for nb in notebook_ids:
                ident(nb)
            notebook_ids = sorted(set(notebook_ids))
        def apply():
            data = self.load()
            before = data['projects'].get(path)
            after = {'provider': 'gemini', 'notebook_ids': notebook_ids} if notebook_ids is not None else None
            if after is None:
                data['projects'].pop(path, None)
            else:
                data['projects'][path] = after
            if not dry_run and before != after:
                write_private(self.path, data)
            return {'status': 'PREVIEW' if dry_run else 'OK', 'project': path,
                    'changed': before != after, 'before': before, 'after': after,
                    'network_operations': 0, 'project_writes': 0}
        if dry_run:
            return apply()
        with self.lock():
            return apply()
