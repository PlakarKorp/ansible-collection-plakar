#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: organization_info
short_description: Read a Plakar organization, its members and its grants
version_added: 0.1.0
description:
  - Reads one organization by name (the API key's own by default), with its
    children and, on request, its members and grants.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  name:
    description:
      - Name of the organization, anywhere in the badge organization's
        subtree. Defaults to the API key's own organization.
    type: str
  include_members:
    description:
      - Also return the members.
    type: bool
    default: false
  include_grants:
    description:
      - Also return the grants.
    type: bool
    default: false
'''

EXAMPLES = r'''
- name: Who is in the Lyon tenant, and what may they do
  plakarkorp.plakar.organization_info:
    name: Lyon
    include_members: true
    include_grants: true
  register: lyon
'''

RETURN = r'''
organization:
  description: The organization (id, name, type, parent_id).
  returned: always
  type: dict
children:
  description: The direct sub-organizations.
  returned: always
  type: list
  elements: dict
members:
  description: The members (user_id, email, account, name, is_service).
  returned: when O(include_members) is true
  type: list
  elements: dict
grants:
  description: The grants (id, subject, role).
  returned: when O(include_grants) is true
  type: list
  elements: dict
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)
from ansible_collections.plakarkorp.plakar.plugins.module_utils.orgs import (
    target_organization)


def main():
    spec = argument_spec()
    spec.update(
        name=dict(type='str'),
        include_members=dict(type='bool', default=False),
        include_grants=dict(type='bool', default=False),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    # target_organization reads the `organization` param; this module calls
    # the same thing `name`, the way the other info modules do.
    module.params['organization'] = module.params.get('name')
    client = PlakarClient(module)
    try:
        org = target_organization(module, client)
        result = {
            'changed': False,
            'organization': {'id': org.get('id'), 'name': org.get('name'),
                             'type': org.get('type'),
                             'parent_id': org.get('parent_id')},
            'children': [
                {'id': c.get('id'), 'name': c.get('name'), 'type': c.get('type')}
                for c in client.child_organizations(org['id'])],
        }
        if module.params.get('include_members'):
            result['members'] = [
                {'user_id': m.get('user_id'), 'email': m.get('email'),
                 'account': m.get('account'), 'name': m.get('name'),
                 'is_service': m.get('is_service')}
                for m in client.list_members(org['id'])]
        if module.params.get('include_grants'):
            result['grants'] = [
                {'id': g.get('id'),
                 'subject': {'type': (g.get('subject') or {}).get('type'),
                             'id': (g.get('subject') or {}).get('id'),
                             'name': (g.get('subject') or {}).get('name'),
                             'email': (g.get('subject') or {}).get('email')},
                 'role': (g.get('role') or {}).get('name')}
                for g in client.list_grants(org['id'])]
        module.exit_json(**result)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
