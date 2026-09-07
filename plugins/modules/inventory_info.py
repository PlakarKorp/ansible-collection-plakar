#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: inventory_info
short_description: Read Plakar inventories and their resources
version_added: 0.1.0
description:
  - Lists the organization's inventories, or reads one inventory by name with
    its coverage summary and, optionally, its resources.
  - Configuration values (provider credentials) are never echoed.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  name:
    description:
      - Name of one inventory to read. Without it, all visible inventories
        are listed.
    type: str
  include_resources:
    description:
      - Also return the resources of the inventory named by O(name).
    type: bool
    default: false
'''

EXAMPLES = r'''
- name: All inventories
  plakarkorp.plakar.inventory_info:
  register: all_inventories

- name: One inventory, with what it holds
  plakarkorp.plakar.inventory_info:
    name: Production Scaleway
    include_resources: true
  register: scaleway
'''

RETURN = r'''
inventories:
  description: The visible inventories, with resource counts and coverage.
  returned: when O(name) is not set
  type: list
  elements: dict
inventory:
  description: The inventory named by O(name), with coverage and summaries.
  returned: when O(name) is set
  type: dict
resources:
  description: The inventory's resources.
  returned: when O(include_resources) is true
  type: list
  elements: dict
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)


def _listing(inventory):
    return {
        'id': inventory.get('id'),
        'name': inventory.get('name'),
        'type': inventory.get('type'),
        'count': inventory.get('count'),
        'last_update': inventory.get('last_update'),
        'residency': inventory.get('residency'),
        'coverage': inventory.get('coverage'),
    }


def main():
    spec = argument_spec()
    spec.update(
        name=dict(type='str'),
        include_resources=dict(type='bool', default=False),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    if module.params.get('include_resources') and not module.params.get('name'):
        module.fail_json(msg='include_resources needs name to say which inventory')
    client = PlakarClient(module)
    try:
        if not module.params.get('name'):
            items = client.list_inventories()
            module.exit_json(changed=False,
                             inventories=[_listing(i) for i in items])

        found = client.inventory_by_name(module.params['name'])
        detail = client.request('GET', '/api/v1/inventories/%s' % found['id'])
        # The detail echoes provider configuration, credentials included;
        # an info module has no business handing those back to a play.
        inventory = {
            'id': detail.get('id'),
            'name': detail.get('name'),
            'type': detail.get('type'),
            'last_update': detail.get('last_update'),
            'residency': detail.get('residency'),
            'summaries': detail.get('summaries'),
            'coverage': detail.get('coverage'),
        }
        result = {'changed': False, 'inventory': inventory}
        if module.params.get('include_resources'):
            result['resources'] = client.inventory_resources(found['id'])
        module.exit_json(**result)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
