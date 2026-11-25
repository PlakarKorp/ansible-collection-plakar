# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

# Implementation of the secret_provider module: name-keyed idempotency, the
# choice of a protocol among those the integration declares, and the v1 wart
# that update is a PUT replacing the whole field map — a field left out is
# deleted, the credential with it — so an update merges the playbook's values
# over the provider's current state.

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarError, keeps_secret)
from ansible_collections.plakarkorp.plakar.plugins.module_utils.connectors import (
    _fields_differ, _value_str)


def _fields_to_api(module, raw):
    """{key: value} -> API shape. A secret provider's fields are plain values:
    its credential is the one secret that cannot come from a secret provider."""
    out = {}
    for key, value in (raw or {}).items():
        if isinstance(value, (dict, list)):
            module.fail_json(msg='fields.%s must be a plain value' % key)
        out[key] = {'value': _value_str(value)}
    return out


def _protocol(client, integration, configured):
    """The protocol to use: the configured one, checked against what the
    integration declares, or the integration's only one.

    Unlike a store's, it does not share the integration's name (vault speaks
    vault-sm), and the API answers an unknown one with a 500.
    """
    name = integration.get('name')
    protocols = client.integration_protocols(integration['id'], 'secret_provider')
    schemes = ', '.join(sorted(repr(p.get('scheme')) for p in protocols))
    if configured:
        for protocol in protocols:
            if protocol.get('scheme') == configured:
                return protocol
        raise PlakarError('integration %r has no secret provider protocol %r — it '
                          'declares: %s' % (name, configured, schemes or '(none)'))
    if not protocols:
        raise PlakarError('integration %r cannot back a secret provider' % name)
    if len(protocols) > 1:
        raise PlakarError('integration %r declares several secret provider protocols '
                          '(%s) — set protocol' % (name, schemes))
    return protocols[0]


def _slim(provider):
    return {
        'id': provider.get('id'),
        'name': provider.get('name'),
        'protocol': provider.get('protocol'),
        'integration': (provider.get('integration') or {}).get('name'),
    }


def run_secret_provider_module(module, client):
    params = module.params
    name = params['name']

    current = client.find_secret_provider(name)

    if params['state'] == 'absent':
        if current is None:
            module.exit_json(changed=False)
        if not module.check_mode:
            client.request('DELETE', '/api/v1/secret_providers/%s' % current['id'],
                           ok=(200, 204))
        module.exit_json(changed=True, secret_provider={'id': current.get('id'), 'name': name})

    desired = _fields_to_api(module, params.get('fields'))

    if current is None:
        if not params.get('integration'):
            module.fail_json(msg='integration is required to create secret provider %r' % name)
        integration = client.installed_integration(params['integration'])
        protocol = _protocol(client, integration, params.get('protocol'))
        # The API refuses the whole request without naming what is missing.
        missing = sorted(f['name'] for f in (protocol.get('fields') or [])
                         if f.get('required') and f.get('name') not in desired)
        if missing:
            module.fail_json(msg='protocol %s requires fields: %s'
                                 % (protocol['scheme'], ', '.join(missing)))

        if module.check_mode:
            module.exit_json(changed=True, secret_provider={
                'name': name, 'protocol': protocol['scheme'],
                'integration': integration.get('name')})

        created = client.request(
            'POST', '/api/v1/account/organizations/%s/secret_providers' % client.org_id(),
            body={
                'name': name,
                'protocol': protocol['scheme'],
                'integration': {'id': integration['id']},
                'fields': desired,
            }, ok=(200, 201))
        module.exit_json(changed=True, secret_provider={
            'id': created.get('id'), 'name': name, 'protocol': protocol['scheme'],
            'integration': integration.get('name')})

    # present, and it exists. The listing leaves the protocol out: read it.
    detail = client.request('GET', '/api/v1/secret_providers/%s' % current['id'])
    integration = detail.get('integration') or {}
    if params.get('integration') and params['integration'] != integration.get('name'):
        module.fail_json(msg='secret provider %r is backed by integration %r; the '
                             'integration is immutable — delete and recreate to change it'
                             % (name, integration.get('name')))

    # Diff only what the playbook sets, less the secrets the API does not show.
    current_fields = detail.get('fields') or {}
    desired = dict(
        (key, want) for key, want in desired.items()
        if not keeps_secret(want, current_fields.get(key), params['update_secrets']))
    changes = []
    if desired and _fields_differ(desired, current_fields):
        changes.append('fields')
    scheme = detail.get('protocol')
    if params.get('protocol') and params['protocol'] != scheme:
        scheme = _protocol(client, integration, params['protocol'])['scheme']
        changes.append('protocol')

    if not changes:
        module.exit_json(changed=False, secret_provider=_slim(detail))

    if module.check_mode:
        module.exit_json(changed=True, secret_provider=_slim(detail), diff_keys=changes)

    merged = dict(current_fields)
    merged.update(desired)
    client.request('PUT', '/api/v1/secret_providers/%s' % current['id'], body={
        'name': name,
        'protocol': scheme,
        'integration': {'id': integration.get('id')},
        'fields': merged,
    }, ok=(200, 204))
    module.exit_json(changed=True, secret_provider=_slim(detail), diff_keys=changes)
