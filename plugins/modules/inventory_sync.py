#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: inventory_sync
short_description: Synchronize a Plakar inventory against its provider
version_added: 0.9.1
description:
  - Triggers a synchronization of an inventory, re-reading what its provider
    holds and updating the resource set accordingly. The call is synchronous
    and returns once the provider has been consulted.
  - A sync always re-reads the provider, so the task always reports changed.
  - Self-managed inventories hold only what playbooks declare
    (M(plakarkorp.plakar.inventory_resource)); syncing one succeeds without
    effect.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  name:
    description:
      - Name of the inventory to synchronize.
    type: str
    required: true
'''

EXAMPLES = r'''
- name: Refresh what the Scaleway project holds
  plakarkorp.plakar.inventory_sync:
    name: Production Scaleway
'''

RETURN = r'''
inventory:
  description: The inventory that was synchronized.
  returned: always
  type: dict
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)


def main():
    spec = argument_spec()
    spec.update(name=dict(type='str', required=True))
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)
    try:
        inventory = client.inventory_by_name(module.params['name'])
        slim = {'id': inventory.get('id'), 'name': inventory.get('name'),
                'type': inventory.get('type')}
        if module.check_mode:
            module.exit_json(changed=True, inventory=slim)
        # The v1 sync endpoint is a GET that mutates; it answers 200 either
        # way and carries the failure in the body.
        res = client.request('GET', '/api/v1/inventories/%s/sync' % inventory['id'])
        if not (res or {}).get('ok'):
            module.fail_json(msg=(res or {}).get('error') or 'inventory sync failed',
                             inventory=slim)
        module.exit_json(changed=True, inventory=slim)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
