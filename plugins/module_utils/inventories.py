# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

# Shared implementation of the inventory module: name-keyed idempotency
# against the paginated listing, the provider-specific configuration blocks
# (flat playbook keys wrapped into the API's ConfigurationField shape), and
# the v1 wart that update is a full-body POST on the inventory id — so an
# update merges the playbook's values over the inventory's current state.

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import PlakarError

# Per provider: the JSON key of its configuration block and its fields.
# 'cf' fields travel as {'value': ...} (a ConfigurationField, optionally
# carrying a secret provider); 'str' fields are plain strings on the wire.
# The distinction is a v1 wire detail — playbooks pass flat values either way.
PROVIDERS = {
    'aws': ('aws_configuration', {
        'credentials_type': 'str',
        'region': 'str',
        'access_key': 'cf',
        'secret_access_key': 'cf',
    }),
    'ovh': ('ovh_configuration', {
        'application_key': 'cf',
        'application_secret': 'cf',
        'consumer_key': 'cf',
        'endpoint': 'str',
    }),
    'scaleway': ('scaleway_configuration', {
        'scw_project_id': 'cf',
        'scw_access_key': 'cf',
        'scw_secret_key': 'cf',
    }),
    'gcp': ('gcp_configuration', {
        'gcp_project_id': 'cf',
        'gcp_service_account_json': 'cf',
    }),
    'k8s': ('k8s_configuration', {
        'k8s_kubeconf': 'cf',
    }),
    'vmware': ('vmware_configuration', {
        'vsphere_server': 'cf',
        'vsphere_username': 'cf',
        'vsphere_password': 'cf',
        'vsphere_tls_skip_verify': 'str',
        'vsphere_tls_ca_bundle': 'cf',
    }),
    'self-managed': (None, {}),
}


def inventory_types():
    return sorted(PROVIDERS)


def _value_str(value):
    # Field values travel as strings; booleans go JSON-style so a playbook's
    # `use_tls: false` round-trips against what the API and UI write.
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def _field_to_api(value):
    """'v' or {'value': ..., 'provider_id': ...} -> ConfigurationField JSON."""
    if isinstance(value, dict):
        field = {'value': _value_str(value.get('value', ''))}
        if value.get('provider_id'):
            field['provider'] = {'id': value['provider_id']}
        return field
    return {'value': _value_str(value)}


def config_to_api(inv_type, raw):
    """Playbook configuration (flat mapping) -> the provider's JSON block."""
    fields = PROVIDERS[inv_type][1]
    raw = raw or {}
    unknown = sorted(set(raw) - set(fields))
    if unknown:
        raise PlakarError('unknown %s configuration key(s): %s — known: %s'
                          % (inv_type, ', '.join(unknown), ', '.join(sorted(fields))))
    out = {}
    for key, value in raw.items():
        if fields[key] == 'cf':
            out[key] = _field_to_api(value)
        else:
            out[key] = _value_str(value)
    return out


def config_diff_keys(inv_type, desired, current):
    """The desired keys whose values differ; only playbook-named keys count."""
    fields = PROVIDERS[inv_type][1]
    current = current or {}
    differ = []
    for key, want in desired.items():
        have = current.get(key)
        if fields[key] == 'cf':
            have = have or {}
            want_provider = (want.get('provider') or {}).get('id')
            have_provider = (have.get('provider') or {}).get('id')
            if have.get('value') != want['value'] or (
                    want_provider is not None and want_provider != have_provider):
                differ.append(key)
        elif (have or '') != want:
            differ.append(key)
    return differ


def _merged_config(inv_type, desired, current):
    """Full config block for the v1 full-body update: desired over current."""
    fields = PROVIDERS[inv_type][1]
    current = current or {}
    merged = {}
    for key, kind in fields.items():
        if key in desired:
            merged[key] = desired[key]
        elif kind == 'cf':
            have = current.get(key) or {}
            field = {'value': have.get('value') or ''}
            if (have.get('provider') or {}).get('id'):
                field['provider'] = {'id': have['provider']['id']}
            merged[key] = field
        else:
            merged[key] = current.get(key) or ''
    return merged


def _slim(inventory):
    return {
        'id': inventory.get('id'),
        'name': inventory.get('name'),
        'type': inventory.get('type'),
    }


def run_inventory_module(module, client):
    params = module.params
    name = params['name']
    inv_type = params.get('type')

    current = client.find_inventory(name)

    if params['state'] == 'absent':
        if current is None:
            module.exit_json(changed=False)
        if not module.check_mode:
            client.request('DELETE', '/api/v1/inventories/%s' % current['id'],
                           ok=(200, 204))
        module.exit_json(changed=True, inventory=_slim(current))

    if current is None:
        if not inv_type:
            module.fail_json(msg='type is required to create inventory %r' % name)
        config_key = PROVIDERS[inv_type][0]
        desired = config_to_api(inv_type, params.get('configuration'))
        if desired and not config_key:
            module.fail_json(msg='%s inventories take no configuration' % inv_type)

        body = {'name': name, 'type': inv_type}
        if config_key:
            body[config_key] = desired

        if module.check_mode:
            module.exit_json(changed=True, inventory={'name': name, 'type': inv_type})

        created = client.request(
            'POST', '/api/v1/account/organizations/%s/inventories' % client.org_id(),
            body=body, ok=(200, 201))
        module.exit_json(changed=True, inventory={
            'id': created.get('id'), 'name': name, 'type': inv_type})

    # present, and it exists: diff only what the playbook sets.
    current_type = current.get('type')
    if inv_type and inv_type != current_type:
        module.fail_json(msg='inventory %r is of type %r; the type is immutable — '
                             'delete and recreate to change it' % (name, current_type))
    inv_type = current_type
    if inv_type not in PROVIDERS:
        module.fail_json(msg='inventory %r is of type %r, which this module does '
                             'not know how to manage' % (name, inv_type))

    config_key = PROVIDERS[inv_type][0]
    desired = config_to_api(inv_type, params.get('configuration'))
    if desired and not config_key:
        module.fail_json(msg='%s inventories take no configuration' % inv_type)
    if not desired:
        module.exit_json(changed=False, inventory=_slim(current))

    detail = client.request('GET', '/api/v1/inventories/%s' % current['id'])
    have = detail.get(config_key) or {}
    diff = config_diff_keys(inv_type, desired, have)
    if not diff:
        module.exit_json(changed=False, inventory=_slim(current))

    if module.check_mode:
        module.exit_json(changed=True, inventory=_slim(current), diff_keys=sorted(diff))

    # v1 update is POST with a full create-shaped body: merge the playbook's
    # values over the inventory's current state so unset fields stay put.
    body = {
        'name': name,
        'type': inv_type,
        config_key: _merged_config(inv_type, desired, have),
    }
    client.request('POST', '/api/v1/inventories/%s' % current['id'], body=body)
    module.exit_json(changed=True, inventory=_slim(current), diff_keys=sorted(diff))
