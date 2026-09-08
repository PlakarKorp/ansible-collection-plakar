#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: organization
short_description: Manage Plakar organizations
version_added: 0.9.1
description:
  - Creates and deletes organizations under the API key's organization.
  - Organizations are matched by name across the badge organization's
    subtree; the name is the playbook's key, so it must be unique there.
  - There is no update — the name is the key, and O(info) and O(type) are
    set at creation. An organization that already exists is left as it is.
  - Membership is managed with M(plakarkorp.plakar.member), permissions
    with M(plakarkorp.plakar.grant).
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  name:
    description:
      - Name of the organization.
    type: str
    required: true
  state:
    description:
      - Whether the organization should exist.
    type: str
    default: present
    choices: [present, absent]
  parent:
    description:
      - Name of the parent organization. Defaults to the API key's own
        organization.
    type: str
  type:
    description:
      - Organization type. Only C(enterprise) organizations can be created
        as sub-organizations today.
    type: str
    default: enterprise
  info:
    description:
      - Free-form key/value information attached at creation.
    type: dict
'''

EXAMPLES = r'''
- name: A tenant for the Lyon subsidiary
  plakarkorp.plakar.organization:
    name: Lyon

- name: A perimeter nested under it
  plakarkorp.plakar.organization:
    name: Lyon production
    parent: Lyon

- name: Retire it
  plakarkorp.plakar.organization:
    name: Lyon production
    state: absent
'''

RETURN = r'''
organization:
  description: The organization acted on (id, name, type, parent_id).
  returned: when the organization exists or was created
  type: dict
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)
from ansible_collections.plakarkorp.plakar.plugins.module_utils.orgs import (
    run_organization_module)


def main():
    spec = argument_spec()
    spec.update(
        name=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        parent=dict(type='str'),
        type=dict(type='str', default='enterprise'),
        info=dict(type='dict'),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)
    try:
        run_organization_module(module, client)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
