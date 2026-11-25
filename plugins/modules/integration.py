#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: integration
short_description: Install Plakar integrations from the catalog
version_added: 0.9.4
description:
  - Installs an integration from the catalog of the Plakar Control Plane and
    makes that version the current one, or uninstalls it. An integration is
    what lets Plakar speak to a kind of resource, for example C(s3),
    C(sftp) or C(vault).
  - Integrations belong to the deployment, not to an organization.
    Installing and uninstalling need the C(platform-admin) role, and an
    uninstall takes the integration away from every organization.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  name:
    description:
      - Name of the integration in the catalog, for example C(s3).
    type: str
    required: true
  state:
    description:
      - Whether the integration should be installed.
      - V(absent) uninstalls every installed version of it. The stores and
        connectors that use it stop working.
    type: str
    default: present
    choices: [present, absent]
  version:
    description:
      - Version to install and make current, for example C(v1.1.13). Pinning
        it is the deterministic choice.
      - Left out, an integration that is already installed is left on its
        current version, never upgraded. One that is not is installed at
        the highest version the catalog offers, in semantic-version order.
        The catalog marks no version as stable, so that may be a prerelease.
    type: str
'''

EXAMPLES = r'''
- name: The s3 integration, whichever version is there
  plakarkorp.plakar.integration:
    name: s3

- name: Vault, pinned
  plakarkorp.plakar.integration:
    name: vault
    version: v1.1.13

- name: Retire an integration nothing uses any more
  plakarkorp.plakar.integration:
    name: sftp
    state: absent
'''

RETURN = r'''
integration:
  description: The version that is current after the task, with its C(id),
    C(name) and C(version). With O(state=absent), the name and the versions
    that were uninstalled.
  returned: when the integration is installed, or was uninstalled
  type: dict
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)


def _version_key(version):
    """Sort key in semantic-version order: numeric parts first, a final
    release after its prereleases, numeric prerelease identifiers before
    alphanumeric ones."""
    core, _dash, pre = version.lstrip('v').partition('-')
    numbers = [int(p) if p.isdigit() else 0 for p in core.split('.')]
    numbers += [0] * (3 - len(numbers))
    if not pre:
        return (numbers, 1, [])
    return (numbers, 0, [(0, int(p), '') if p.isdigit() else (1, 0, p)
                         for p in pre.split('.')])


def _slim(row):
    return {'id': row.get('id'), 'name': row.get('name'), 'version': row.get('version')}


def _deployment_request(client, method, path, body=None):
    """A write on the deployment itself: a 403 says which role it takes."""
    try:
        return client.request(method, path, body=body, ok=(200, 201, 204))
    except PlakarError as e:
        if e.status != 403:
            raise
        raise PlakarError('%s — installing and uninstalling integrations takes the '
                          'platform-admin role on the deployment' % e.msg, status=403)


def run(module, client):
    params = module.params
    name, version = params['name'], params.get('version')

    installed = client.installed_versions(name)

    if params['state'] == 'absent':
        if not installed:
            module.exit_json(changed=False)
        if not module.check_mode:
            for row in installed:
                _deployment_request(client, 'DELETE',
                                    '/api/v1/integrations/installed/%s' % row['id'])
        module.exit_json(changed=True, integration={
            'name': name, 'versions': sorted(r.get('version') for r in installed)})

    current = [r for r in installed if r.get('is_current')]
    if len(current) > 1:
        raise PlakarError('%d versions of integration %r are current' % (len(current), name))
    if current and version in (None, current[0].get('version')):
        module.exit_json(changed=False, integration=_slim(current[0]))

    # The install route answers an unknown name or version with a bare 500:
    # both are checked against the catalog first.
    offered = client.catalog_versions(name)
    if not offered:
        raise PlakarError('the catalog has no integration named %r' % name)
    if version is None:
        version = max(offered, key=_version_key)
    elif version not in offered:
        raise PlakarError('the catalog has no version %r of %r — it offers: %s'
                          % (version, name, ', '.join(sorted(offered, key=_version_key))))

    if module.check_mode:
        module.exit_json(changed=True, integration={'name': name, 'version': version})

    res = _deployment_request(client, 'POST', '/api/v1/integrations/installed/current',
                              body={'name': name, 'version': version})
    module.exit_json(changed=True, integration={
        'id': (res or {}).get('id'), 'name': name, 'version': version})


def main():
    spec = argument_spec()
    spec.update(
        name=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        version=dict(type='str'),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)
    try:
        run(module, client)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
