"""Prepare a local native-profile distribution; installation stays with the host."""
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

try:
    from ..core.model import KitError, valid_id
except ImportError:
    from core.model import KitError, valid_id


def _profile_home(name):
    from hermes_constants import get_default_hermes_root
    root = (Path(get_default_hermes_root()) / 'profiles').resolve()
    home = (root / name).resolve()
    if not home.is_relative_to(root):
        raise KitError('generated profile must remain inside the host profiles directory')
    return home


def _reload(home):
    sibling = Path(sys.executable).with_name('hermes.exe' if sys.platform == 'win32' else 'hermes')
    executable = str(sibling) if sibling.is_file() else shutil.which('hermes')
    if not executable:
        raise KitError('the host Hermes CLI is required to refresh the generated profile')
    receipts = []
    for action in ('disable', 'enable'):
        command = [executable, '-p', home.name, 'plugins', action, 'adeptory']
        # Enabling can prepare declared dependencies in a cold host environment.
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf8', errors='replace', timeout=600)
        receipts.append({'command': command, 'exit_code': result.returncode,
                         'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            return {'reloaded': False, 'commands': receipts,
                    'error': 'Resolve the host CLI response and enable Adeptory in the target profile before continuing.'}
    message = ' '.join(result.stdout.lower().split())
    return {'reloaded': 'gateway reloaded plugins' in message, 'commands': receipts}


def complete_delivery(kit_id, profile_name, plan):
    target = installed(kit_id, profile_name)
    path = Path(target['library']) / 'build-plan.json'
    seed = Path(target['home']) / 'plugins' / 'adeptory' / 'starter-library' / kit_id / 'build-plan.json'
    if seed.is_file() and path.is_file() and path.read_bytes() == seed.read_bytes():
        try:
            from ..core.library import atomic_json
        except ImportError:
            from core.library import atomic_json
        atomic_json(path, plan)
    return target


def refresh(kit_id, profile_name):
    """Refresh native tool exposure for an installed distribution of this specialist."""
    profile_name = valid_id(profile_name)
    home = Path(_profile_home(profile_name)).resolve()
    starter = home / 'plugins' / 'adeptory' / 'starter-kit.json'
    if starter.is_file():
        if not starter.resolve().is_relative_to(home):
            raise KitError('target profile starter must stay inside its profile')
        data = json.loads(starter.read_text(encoding='utf8'))
        if data.get('id') != kit_id or data.get('scope', {}).get('import_origin', {}).get('kit_id') != kit_id:
            raise KitError('target profile belongs to a different specialist')
    else:
        installed(kit_id, profile_name)
    answer = _reload(home)
    ready = bool(answer and answer.get('reloaded'))
    return {'profile_name': profile_name, 'kit_id': kit_id, 'profile_home': str(home),
            'status': 'profile-reloaded' if ready else 'reload-pending', 'host_response': answer,
            'next': 'Verify tool discovery and a library search/read in a fresh target-profile session.' if ready else
                    'Resolve the host reload response before claiming the installed profile is ready.',
            'scope': 'Public Hermes CLI disable/enable for this generated profile; user adoption and observed task success retain separate evidence.'}


def installed(kit_id, profile_name, expected=None, fingerprint=None):
    profile_name = valid_id(profile_name)
    home = _profile_home(profile_name)
    starter = home / 'plugins' / 'adeptory' / 'starter-kit.json'
    seed = json.loads(starter.read_text(encoding='utf8')) if starter.is_file() else None
    if seed is not None and seed.get('id') != kit_id:
        raise KitError('install the generated specialist in its final Hermes profile first')
    active = home / 'plugin-data' / 'adeptory' / 'kits' / kit_id / 'kit.json'
    library = home / 'library' / kit_id / 'manifest.json'
    if not active.is_file() or not library.is_file():
        raise KitError('verify that the installed profile loads its specialist and own library')
    saved = json.loads(active.read_text(encoding='utf8'))
    if saved.get('scope', {}).get('import_origin', {}).get('kit_id') != kit_id:
        raise KitError('target profile must contain the generated specialist identity')
    if saved.get('adoption', {}).get('origin') != 'verified-user-build-request':
        raise KitError('the installed profile must load the completed, request-authorized specialist')
    if expected is not None:
        snapshot = seed if seed is not None else saved
        origin = snapshot.get('scope', {}).get('import_origin', {})
        def content(data):
            data = json.loads(json.dumps(data))
            data.pop('version', None)
            data.pop('adoption', None)
            data.get('scope', {}).pop('import_origin', None)
            return data
        if (origin.get('version') != expected.version
                or content(snapshot) != content(expected.to_dict())
                or content(saved) != content(snapshot)):
            raise KitError('the installed specialist differs from the current package; prepare and install a refreshed distribution')
        if fingerprint is not None:
            try:
                from ..core.library import KnowledgeLibrary
            except ImportError:
                from core.library import KnowledgeLibrary
            if KnowledgeLibrary(home / 'library').fingerprint(kit_id) != fingerprint:
                raise KitError('the installed library differs from the current package; refresh the distribution')
    return {'name': profile_name, 'home': str(home), 'library': str(library.parent), 'kit_id': kit_id}


def prepare(store, library, kit_id, profile_name, host_settings=None):
    import yaml
    profile_name = valid_id(profile_name)
    kit = store.load(kit_id)
    destination = library.root / '_profile-bundles' / (profile_name + '-' + uuid.uuid4().hex[:8])
    store.export(kit_id, destination)
    shutil.copy2(destination / 'runtime' / 'SOUL.md', destination / 'SOUL.md')
    plugin_root = Path(__file__).resolve().parents[1]
    target = destination / 'plugins' / 'adeptory'
    files = [plugin_root / p for p in ('__init__.py', 'plugin.yaml', 'README.md')]
    if (plugin_root / 'LICENSE').is_file():
        files.append(plugin_root / 'LICENSE')
    for folder in ('core', 'adapter_hermes', 'skills', 'docs'):
        files += [p for p in (plugin_root / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    for source in files:
        if source.is_symlink() or not source.resolve().is_relative_to(plugin_root):
            raise ValueError('plugin bundle contains an escaping source path')
        copy = target / source.relative_to(plugin_root)
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, copy)
    starter = kit.to_dict()
    starter['version'] = 1
    starter['scope']['import_origin'] = {'kit_id': kit.id, 'version': kit.version}
    starter['adoption'] = {'status': 'proposed', 'origin': 'none', 'choices': {}}
    (target / 'starter-kit.json').write_text(json.dumps(starter, ensure_ascii=False, indent=2), encoding='utf8')
    if kit.adoption.origin == 'verified-user-build-request':
        authority = {'origin': kit.adoption.origin, 'actor': kit.adoption.actor,
                     'choices': kit.adoption.choices,
                     'starter_sha256': hashlib.sha256((target / 'starter-kit.json').read_bytes()).hexdigest()}
        (target / 'starter-authority.json').write_text(json.dumps(authority, ensure_ascii=False, indent=2), encoding='utf8')
    if (destination / 'library').exists():
        shutil.copytree(destination / 'library', target / 'starter-library')
    if host_settings is None:
        host_path = library.root.parent / 'config.yaml'
        host_settings = yaml.safe_load(host_path.read_text(encoding='utf8')) if host_path.exists() else {}
    config = {'plugins': {'enabled': ['adeptory']},
              'platform_toolsets': {'cli': ['hermes-cli', 'adeptory']}}
    if type(host_settings.get('_config_version')) is int:
        config['_config_version'] = host_settings['_config_version']
    model = host_settings.get('model', {})
    if isinstance(model, dict):
        selection = {key: model[key] for key in ('provider', 'default')
                     if isinstance(model.get(key), str) and model[key].strip()}
        if selection:
            config['model'] = selection
    (destination / 'config.yaml').write_text(yaml.safe_dump(config), encoding='utf8')
    manifest = {'name': profile_name, 'version': '0.1.0', 'description': kit.goal,
                'hermes_requires': '>=0.23.1',
                'distribution_owned': ['SOUL.md', 'config.yaml', 'plugins']}
    (destination / 'distribution.yaml').write_text(yaml.safe_dump(manifest, sort_keys=False), encoding='utf8')
    sibling = Path(sys.executable).with_name('hermes.exe' if sys.platform == 'win32' else 'hermes')
    executable = str(sibling) if sibling.is_file() else (shutil.which('hermes') or 'hermes')
    return {'profile_name': profile_name, 'directory': str(destination), 'kit_id': kit_id,
            'installation': [executable, 'profile', 'install', str(destination), '--name', profile_name],
            'verification_cli': [executable, '-p', profile_name, 'chat', '--oneshot', '--format', 'stream-json'],
            'after_install': {'tool': 'adeptory_build', 'operation': 'refresh_profile',
                              'kit_id': kit_id, 'profile_name': profile_name},
            'status': 'prepared-local-distribution',
            'remaining': ['Host profile installation', 'Provider/credential setup through the host',
                          'Host instruction and protection-policy setup and verification',
                          'Native plugin loading and any required host reload',
                          'Original-request authorization in the installed profile', 'Native task verification']}
