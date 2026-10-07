"""Read only the deployment's hash-verified source inventory, never arbitrary paths."""
import hashlib
import json
from pathlib import Path, PurePosixPath


ROOT_DOCS = {'AGENTS.md', 'README.md', 'PROJECT_SPEC.md', 'ARCHITECTURE.md', 'docs/阿里云试运行与运维助手.md'}
SOURCE_SUFFIXES = {'.py', '.js', '.mjs', '.css', '.html', '.md', '.json'}


def allowed_name(name):
    path = PurePosixPath(name)
    return (not path.is_absolute() and '\\' not in name and not any(p.startswith('.') for p in path.parts)
            and (name in ROOT_DOCS or len(path.parts) >= 2 and path.parts[0] in {'app', 'web', 'scripts'})
            and path.suffix in SOURCE_SUFFIXES and path.name not in {'workflow-guides.json', 'workflow-handbook.html'})


def build_manifest(root, base_sha):
    root = Path(root).resolve()
    files = {}
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if path.is_file() and not path.is_symlink() and allowed_name(name) and path.stat().st_size <= 512_000:
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {'base_sha': base_sha, 'release_id': digest, 'files': files}


class SourceContext:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.manifest = json.loads((self.root / 'ops-source-manifest.json').read_text(encoding='utf-8'))
        self.files = self.manifest['files']
        if not self.files or any(not allowed_name(n) for n in self.files):
            raise RuntimeError('Invalid source inventory')
        digest = hashlib.sha256(json.dumps(self.files, sort_keys=True).encode()).hexdigest()
        if digest != self.manifest['release_id']:
            raise RuntimeError('Invalid source fingerprint')
        self.release_id = digest

    def _text(self, name):
        if name not in self.files:
            raise ValueError('Path is outside the approved source inventory')
        path = self.root / name
        if any(p.is_symlink() for p in [path, *path.parents] if p != self.root.parent):
            raise ValueError('Symbolic links are not source context')
        if not path.resolve().is_relative_to(self.root) or path.stat().st_size > 512_000:
            raise ValueError('Invalid source file')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.files[name]:
            raise RuntimeError('Source changed after deployment')
        return raw.decode('utf-8-sig')

    def snapshot(self):
        return {'release_id': self.release_id, 'base_sha': self.manifest['base_sha'],
                'source_directory': str(self.root),
                'candidate_bundle': '/opt/huakangos/handoff/candidate.bundle',
                'candidate_branch': 'main',
                'review_handoff': 'Read deployed files through MCP; authenticated Cutie may retrieve this exact release over SSH. Apply changes in a GitHub checkout, verify base SHA and open a PR; the owner merges.',
                'source_files': len(self.files), 'roots': sorted(ROOT_DOCS),
                'components': ['app/main.py', 'web/app.js', 'app/ops_feedback_api.py',
                               'app/ops_store.py', 'app/ops_worker.py', 'app/ops_mcp.py'],
                'architecture': self._text('docs/阿里云试运行与运维助手.md')[:7000],
                'business_contract': self._text('ARCHITECTURE.md')[:2500],
                'boundary': 'Read-only deployed source; code proposals require Cutie review and a user-merged GitHub PR.'}

    def read(self, path, start_line=1, line_count=70):
        if type(start_line) is not int or type(line_count) is not int or start_line < 1 or not 1 <= line_count <= 100:
            raise ValueError('Invalid line window')
        lines = self._text(path).splitlines()
        chosen = lines[start_line - 1:start_line - 1 + line_count]
        content = '\n'.join(f'{i}: {line}' for i, line in enumerate(chosen, start_line))
        if len(content) > 12000:
            raise ValueError('Requested lines exceed context budget; select a smaller window')
        return {'path': path, 'sha256': self.files[path], 'release_id': self.release_id,
                'start_line': start_line, 'total_lines': len(lines), 'content': content}

    def search(self, query, limit=12):
        if not isinstance(query, str) or not 2 <= len(query) <= 100 or type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError('Invalid literal source query')
        matches = []
        for name in sorted(self.files):
            content = self._text(name)
            for number, line in enumerate(content.splitlines(), 1):
                if query.casefold() in line.casefold() or query.casefold() in name.casefold() and number == 1:
                    matches.append({'path': name, 'line': number, 'text': line[:700], 'sha256': self.files[name]})
                    if len(matches) == limit:
                        return {'matches': matches, 'limited': True, 'release_id': self.release_id}
        return {'matches': matches, 'limited': False, 'release_id': self.release_id}
