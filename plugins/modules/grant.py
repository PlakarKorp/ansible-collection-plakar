#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: grant
short_description: Manage role grants in a Plakar organization
version_added: 0.1.0
description:
  - Grants a role to a member of an organization, and revokes it.
  - A grant is one (subject, role) pair; a member can hold several. The
    module manages exactly the pair the playbook names and touches nothing
    else the subject holds.
  - The subject must already be a member — see M(plakarkorp.plakar.member).
  - The role names come from the server's catalogue; the standard tier is
    C(owner), C(administrator), C(operator) and C(auditor). An unknown role
    fails with the catalogue's list.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  organization:
    description:
      - Name of the organization the grant lives in. Defaults to the API
        key's own organization.
    type: str
  state:
    description:
      - Whether the grant should exist.
    type: str
    default: present
    choices: [present, absent]
  subject:
    description:
      - Who holds the grant — a member's email address, or the name of a
        service account (which has no address).
    type: str
    required: true
  role:
    description:
      - Name of the role, as the catalogue spells it, for example
        C(operator) or C(backup-operator).
    type: str
    required: true
'''

EXAMPLES = r'''
- name: Alice audits the Lyon tenant
  plakarkorp.plakar.grant:
    organization: Lyon
    subject: alice@example.com
    role: auditor

- name: The automation runs what is already defined
  plakarkorp.plakar.grant:
    organization: Lyon
    subject: nightly-automation
    role: operator

- name: Alice no longer audits
  plakarkorp.plakar.grant:
    organization: Lyon
    subject: alice@example.com
    role: auditor
    state: absent
'''

RETURN = r'''
grant:
  description: The grant acted on (id, subject, role).
  returned: when the grant exists or was created
  type: dict
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)
from ansible_collections.plakarkorp.plakar.plugins.module_utils.orgs import (
    run_grant_module)


def main():
    spec = argument_spec()
    spec.update(
        organization=dict(type='str'),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        subject=dict(type='str', required=True),
        role=dict(type='str', required=True),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)
    try:
        run_grant_module(module, client)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
