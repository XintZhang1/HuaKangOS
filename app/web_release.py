"""Content versions for the immutable source directory of a running release.

No database, private configuration, cookies or business data participates in a
version. Replacing a release requires restarting Web, as with Python source.
"""
from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
import re

import anyio
from starlette.datastructures import Headers
from starlette.responses import FileResponse, HTMLResponse, Response
from starlette.staticfiles import StaticFiles


REVALIDATE = 'no-cache, max-age=0, must-revalidate'
ASSET_ATTRIBUTE = re.compile(r'(?P<attribute>src|href)="(?P<path>/static/[^"?]+)(?:\?[^\"]*)?"')


class WebRelease:
    def __init__(self, root: Path):
        self.root = root
        self.asset_hashes = {}
        digest = hashlib.sha256()
        # The backend is included so an API-only release also alerts open pages.
        for folder, suffixes in (('app', {'.py', '.json'}), ('web', {'.js', '.css', '.html', '.json'})):
            for path in sorted((root / folder).rglob('*')):
                if not path.is_file() or path.suffix not in suffixes or path.is_symlink():
                    continue
                relative = path.relative_to(root).as_posix()
                content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                digest.update((relative + '\0' + content_hash + '\n').encode('utf-8'))
                if folder == 'web':
                    self.asset_hashes['/static/' + path.relative_to(root / 'web').as_posix()] = content_hash
        self.version = digest.hexdigest()
        template = (root / 'web' / 'index.html').read_text(encoding='utf-8')

        def version_asset(match):
            path = match['path']
            fingerprint = self.asset_hashes.get(path)
            if fingerprint is None:
                raise RuntimeError('Missing versioned web asset: ' + path)
            return f'{match["attribute"]}="{path}?v={fingerprint}"'

        self.html = ASSET_ATTRIBUTE.sub(version_asset, template).replace('__HUAKANGOS_RELEASE__', self.version)

    def home(self):
        return HTMLResponse(self.html, headers={'Cache-Control': 'no-store'})


class ReleaseStaticFiles(StaticFiles):
    def __init__(self, release: WebRelease):
        super().__init__(directory=release.root / 'web')
        self.release = release

    def file_response(self, full_path, stat_result, scope, status_code=200):
        # Preserve StaticFiles' path/method checks, but defer validators to the
        # async content read below: mtime+size can collide across packaged builds.
        return FileResponse(full_path, status_code=status_code, stat_result=stat_result)

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if not isinstance(response, FileResponse):
            return response
        if Path(response.path).resolve() == (self.release.root / 'web' / 'index.html').resolve():
            return self.release.home()
        content = await anyio.to_thread.run_sync(Path(response.path).read_bytes)
        etag = '"' + hashlib.sha256(content).hexdigest() + '"'
        headers = {'Cache-Control': REVALIDATE, 'ETag': etag}
        supplied = Headers(scope=scope).get('if-none-match', '')
        matches = [tag.strip().removeprefix('W/') for tag in supplied.split(',')]
        if etag in matches or '*' in matches:
            return Response(status_code=304, headers=headers)
        # Ignore If-Modified-Since: equal timestamps do not prove equal content.
        media_type = mimetypes.guess_type(response.path)[0] or 'application/octet-stream'
        headers['Content-Length'] = str(len(content))
        return Response(content if scope['method'] != 'HEAD' else b'', media_type=media_type, headers=headers)
