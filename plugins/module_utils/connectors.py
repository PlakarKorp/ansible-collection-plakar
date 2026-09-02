# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

# Shared implementation of the connector and repository modules: name-keyed
# idempotency (list, match by name, diff only what the playbook sets), the
# create/update/delete flow, and the v1 quirk that update is POST on the
# connector id with a full create-shaped body — so an update merges the
# playbook's values over the connector's current state.

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import PlakarError


def connector_options():
    """Options shared by the connector and repository modules."""
    return dict(
        name=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        protocol=dict(type='str'),
        integration=dict(type='str'),
        resource=dict(type='str'),
        fields=dict(type='dict', no_log=True),
        endpoints=dict(type='list', elements='str'),
        data_classes=dict(type='list', elements='str'),
        environment=dict(type='str'),
        temperature=dict(type='str'),
    )


def _value_str(value):
    # Field values travel as strings; booleans go JSON-style so a playbook's
    # `use_tls: false` round-trips against what the API and UI write.
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def _fields_to_api(raw):
    """{key: 'value'} or {key: {'value': ..., 'provider_id': ...}} -> API shape."""
    out = {}
    for key, val in (raw or {}).items():
        if isinstance(val, dict):
            field = {'value': _value_str(val.get('value', ''))}
            if val.get('provider_id'):
                field['provider'] = {'id': val['provider_id']}
            out[key] = field
        else:
            out[key] = {'value': _value_str(val)}
    return out


def _fields_differ(desired, current):
    """Only the keys the playbook names are managed; extra current keys stay."""
    current = current or {}
    for key, want in desired.items():
        have = current.get(key) or {}
        if have.get('value') != want['value']:
            return True
        want_provider = (want.get('provider') or {}).get('id')
        have_provider = (have.get('provider') or {}).get('id')
        if want_provider is not None and want_provider != have_provider:
            return True
    return False


def _slim(connector):
    return {
        'id': connector.get('id'),
        'name': connector.get('name'),
        'type': connector.get('type'),
        'protocol': connector.get('protocol'),
        'environment': connector.get('environment'),
        'data_classes': connector.get('data_classes'),
    }


def run_connector_module(module, client, kind, repository=False):
    params = module.params
    name = params['name']

    current = client.find_connector(kind, name)

    if params['state'] == 'absent':
        if current is None:
            module.exit_json(changed=False)
        if not module.check_mode:
            client.request('DELETE', '/api/v1/connectors/%s' % current['id'],
                           ok=(200, 204))
        module.exit_json(changed=True, connector=_slim(current))

    desired_fields = _fields_to_api(params.get('fields')) if params.get('fields') else {}

    if current is None:
        for required in ('protocol', 'integration', 'resource'):
            if not params.get(required):
                module.fail_json(msg='%s is required to create connector %r' % (required, name))
        integration = client.installed_integration(params['integration'])
        resource = client.resource_ref(params['resource'])

        body = {
            'name': name,
            'type': kind,
            'protocol': params['protocol'],
            'integration': {'id': integration['id']},
            'urn_id': resource['urn_id'],
            'fields': desired_fields,
            'endpoints': [{'endpoint': e} for e in (params.get('endpoints') or [])],
            'data_classes': params.get('data_classes') or [],
            'environment': params.get('environment') or '',
        }
        if params.get('temperature'):
            body['temperature'] = params['temperature']

        if module.check_mode:
            module.exit_json(changed=True, connector={'name': name, 'type': kind})

        created = client.request(
            'POST', '/api/v1/account/organizations/%s/connectors' % client.org_id(),
            body=body, ok=(200, 201))

        initialized = False
        if repository and params.get('initialize'):
            init_body = {}
            if params.get('compression'):
                init_body['compression'] = params['compression']
            client.request('POST', '/api/v1/connectors/%s/stores/create' % created['id'],
                           body=init_body or None, ok=(200, 201, 202, 204))
            initialized = True

        result = _slim(created)
        result['initialized'] = initialized
        module.exit_json(changed=True, connector=result)

    # present, and it exists: diff only what the playbook sets.
    changes = {}
    if desired_fields and _fields_differ(desired_fields, current.get('fields')):
        changes['fields'] = True
    for key, transform in (
            ('protocol', None),
            ('environment', None),
            ('temperature', None),
            ('endpoints', lambda v: sorted(v or [])),
            ('data_classes', lambda v: sorted(v or []))):
        want = params.get(key)
        if want is None:
            continue
        have = current.get(key)
        if key == 'endpoints':
            have = [e.get('endpoint') for e in (have or [])]
        if transform:
            want, have = transform(want), transform(have)
        if want != have:
            changes[key] = True

    if not changes:
        module.exit_json(changed=False, connector=_slim(current))

    if module.check_mode:
        module.exit_json(changed=True, connector=_slim(current),
                         diff_keys=sorted(changes))

    # v1 update is POST with a full create-shaped body: merge the playbook's
    # values over the connector's current state so unset options stay put.
    merged_fields = dict(current.get('fields') or {})
    merged_fields.update(desired_fields)
    endpoints = params.get('endpoints')
    if endpoints is None:
        endpoints = [e.get('endpoint') for e in (current.get('endpoints') or [])]
    resource = current.get('resource') or {}
    body = {
        'name': name,
        'type': kind,
        'protocol': params.get('protocol') or current.get('protocol'),
        'integration': {'id': (current.get('integration') or {}).get('id')},
        'urn_id': resource.get('urn_id'),
        'fields': merged_fields,
        'endpoints': [{'endpoint': e} for e in endpoints],
        'data_classes': params.get('data_classes') if params.get('data_classes') is not None
        else (current.get('data_classes') or []),
        'environment': params.get('environment') if params.get('environment') is not None
        else (current.get('environment') or ''),
    }
    temperature = params.get('temperature') or current.get('temperature')
    if temperature:
        body['temperature'] = temperature
    if not body['urn_id']:
        raise PlakarError('connector %r carries no resource urn_id; cannot build the '
                          'full-body update v1 requires' % name)

    client.request('POST', '/api/v1/connectors/%s' % current['id'], body=body)
    module.exit_json(changed=True, connector=_slim(current), diff_keys=sorted(changes))
