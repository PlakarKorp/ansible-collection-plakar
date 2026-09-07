#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: inventory_resource
short_description: Manage resources in a self-managed Plakar inventory
version_added: 0.1.0
description:
  - Declares, updates and deletes resources in a self-managed inventory (see
    M(plakarkorp.plakar.inventory)). Provider-backed inventories are read-only;
    their resources come from synchronization.
  - Resources are matched by URN within the inventory; the URN is the
    playbook's key and is immutable.
  - Only the options the playbook sets are managed on update; anything else
    keeps its current server-side value.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  inventory:
    description:
      - Name of the self-managed inventory holding the resource.
    type: str
    required: true
  urn:
    description:
      - URN identifying the resource, for example C(urn:res-web-tier).
    type: str
    required: true
  state:
    description:
      - Whether the resource should exist.
    type: str
    default: present
    choices: [present, absent]
  name:
    description:
      - Display name of the resource.
      - Required when creating.
    type: str
  class:
    description:
      - Resource class, for example C(object-storage) or C(virtual-machine).
      - Required when creating.
    type: str
  subclass:
    description:
      - Resource subclass, for example C(s3).
    type: str
  service:
    description:
      - Service the resource belongs to.
    type: str
  endpoints:
    description:
      - Endpoints the resource is reachable at, as hostnames or IP addresses.
    type: list
    elements: str
  tags:
    description:
      - Tags on the resource.
    type: list
    elements: str
  excluded_from_coverage:
    description:
      - Whether the resource is left out of coverage accounting.
    type: bool
'''

EXAMPLES = r'''
- name: Declare the database server
  plakarkorp.plakar.inventory_resource:
    inventory: Datacenter racks
    urn: urn:res-db-primary
    name: DB primary
    class: database
    subclass: postgres
    endpoints: [db1.internal]
    tags: [production, database]

- name: Retire it
  plakarkorp.plakar.inventory_resource:
    inventory: Datacenter racks
    urn: urn:res-db-primary
    state: absent
'''

RETURN = r'''
resource:
  description: The resource acted on (a summary).
  returned: when the resource exists or was created
  type: dict
diff_keys:
  description: The option names whose values differed and drove the update.
  returned: on update
  type: list
  elements: str
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)


def _slim(resource):
    return {
        'urn': resource.get('urn'),
        'urn_id': resource.get('urn_id'),
        'name': resource.get('name'),
        'class': resource.get('class'),
        'subclass': resource.get('subclass'),
        'service': resource.get('service'),
        'tags': resource.get('tags') or [],
    }


def _current_endpoints(client, inventory_id, urn_id):
    res = client.request('GET', '/api/v1/inventories/%s/resources/%s/endpoints'
                         % (inventory_id, urn_id))
    return [e.get('endpoint') for e in ((res or {}).get('endpoints') or [])]


def run(module, client):
    params = module.params
    urn = params['urn']

    inventory = client.inventory_by_name(params['inventory'])
    current = client.find_inventory_resource(inventory['id'], urn)

    if params['state'] == 'absent':
        if current is None:
            module.exit_json(changed=False)
        if not module.check_mode:
            client.request('DELETE', '/api/v1/inventories/%s/resources/%s'
                           % (inventory['id'], current['urn_id']), ok=(200, 204))
        module.exit_json(changed=True, resource=_slim(current))

    if current is None:
        for required in ('name', 'class'):
            if not params.get(required):
                module.fail_json(msg='%s is required to create resource %r'
                                 % (required, urn))
        body = {
            'urn': urn,
            'name': params['name'],
            'class': params['class'],
            'subclass': params.get('subclass') or '',
            'service': params.get('service') or '',
            'endpoints': [{'endpoint': e} for e in (params.get('endpoints') or [])],
            'tags': params.get('tags') or [],
            'excluded_from_coverage': bool(params.get('excluded_from_coverage')),
        }
        if module.check_mode:
            module.exit_json(changed=True, resource={'urn': urn, 'name': params['name']})
        created = client.request('POST', '/api/v1/inventories/%s/resources'
                                 % inventory['id'], body=body, ok=(200, 201))
        module.exit_json(changed=True, resource=_slim(created))

    # present, and it exists: diff only what the playbook sets.
    changes = []
    for key, transform in (
            ('name', None),
            ('class', None),
            ('subclass', None),
            ('service', None),
            ('excluded_from_coverage', None),
            ('tags', lambda v: sorted(v or []))):
        want = params.get(key)
        if want is None:
            continue
        have = current.get(key)
        if transform:
            want, have = transform(want), transform(have)
        if want != have:
            changes.append(key)

    endpoints = params.get('endpoints')
    have_endpoints = None
    if endpoints is not None:
        have_endpoints = _current_endpoints(client, inventory['id'], current['urn_id'])
        if sorted(endpoints) != sorted(have_endpoints):
            changes.append('endpoints')

    if not changes:
        module.exit_json(changed=False, resource=_slim(current))

    if module.check_mode:
        module.exit_json(changed=True, resource=_slim(current),
                         diff_keys=sorted(changes))

    # v1 update is a full-body put: merge the playbook's values over the
    # resource's current state so unset options stay put.
    if endpoints is None:
        endpoints = _current_endpoints(client, inventory['id'], current['urn_id'])
    excluded = params.get('excluded_from_coverage')
    if excluded is None:
        excluded = bool(current.get('excluded_from_coverage'))
    body = {
        'urn': urn,
        'name': params.get('name') or current.get('name'),
        'class': params.get('class') or current.get('class'),
        'subclass': params.get('subclass') if params.get('subclass') is not None
        else (current.get('subclass') or ''),
        'service': params.get('service') if params.get('service') is not None
        else (current.get('service') or ''),
        'endpoints': [{'endpoint': e} for e in endpoints],
        'tags': params.get('tags') if params.get('tags') is not None
        else (current.get('tags') or []),
        'excluded_from_coverage': excluded,
    }
    updated = client.request('POST', '/api/v1/inventories/%s/resources/%s'
                             % (inventory['id'], current['urn_id']), body=body)
    module.exit_json(changed=True, resource=_slim(updated or current),
                     diff_keys=sorted(changes))


def main():
    spec = argument_spec()
    spec.update(
        inventory=dict(type='str', required=True),
        urn=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        name=dict(type='str'),
        subclass=dict(type='str'),
        service=dict(type='str'),
        endpoints=dict(type='list', elements='str'),
        tags=dict(type='list', elements='str'),
        excluded_from_coverage=dict(type='bool'),
    )
    spec['class'] = dict(type='str')
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)
    try:
        run(module, client)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
