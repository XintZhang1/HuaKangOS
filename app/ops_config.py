"""Private operations configuration, never loaded by the business web process."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def private_json(path):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file() or path.stat().st_size > 32_000:
        raise RuntimeError('Invalid private configuration file')
    if os.name != 'nt' and path.stat().st_mode & 0o077:
        raise RuntimeError('Operations configuration must have mode 0600')
    result = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(result, dict):
        raise RuntimeError('Invalid private configuration')
    return result


def loopback_url(url, path='/mcp'):
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost'}
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path != path):
        raise RuntimeError('Expected a fixed loopback service endpoint')
    return url


def load_config():
    result = private_json(os.environ.get('OPS_CONFIG', ''))
    for key in ('agent_token', 'worker_token', 'reviewer_token'):
        value = result.get(key)
        if not isinstance(value, str) or len(value) < 40 or any(c.isspace() for c in value):
            raise RuntimeError('Invalid operations role credential')
    if len({result[k] for k in ('agent_token', 'worker_token', 'reviewer_token')}) != 3:
        raise RuntimeError('Operations roles require separate credentials')
    loopback_url(result['mcp_url'])
    loopback_url(result['mail_mcp_url'])
    loopback_url(result['web_health_url'], '/api/health')
    for key in ('source_root', 'state_db', 'mail_client_file', 'deepseek_key_file'):
        if not Path(result[key]).is_absolute():
            raise RuntimeError('Operations paths must be absolute')
    if result.get('model', 'deepseek-flash') not in {'deepseek-flash', 'deepseek-v4-pro'}:
        raise RuntimeError('Unapproved operations model')
    return result
