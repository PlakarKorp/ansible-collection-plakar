#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: member
short_description: Manage the members of a Plakar organization
version_added: 0.1.0
description:
  - Adds people and service accounts to an organization, and removes them.
  - A membership carries no permission — what a member may do is a grant,
    managed with M(plakarkorp.plakar.grant).
  - Adding a person goes through the admin invitation path. A brand-new
    address gets an account with a one-time generated password, returned
    once in RV(generated_password); an address that already has an account
    simply gains the membership.
  - A service account (O(service=true)) is an application user — no email,
    no interactive login; its address is minted server-side. Mint its API
    key in the Plakar UI (an application user cannot mint its own).
  - Removing a member removes the membership, not the person's account.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  organization:
    description:
      - Name of the organization the membership belongs to. Defaults to the
        API key's own organization.
    type: str
  state:
    description:
      - Whether the membership should exist.
    type: str
    default: present
    choices: [present, absent]
  email:
    description:
      - Email address of the person. The playbook's key for people.
    type: str
  name:
    description:
      - Display name. The playbook's key for service accounts, which have
        no address; optional decoration for people.
    type: str
  service:
    description:
      - Add an application user rather than a person.
    type: bool
    default: false
'''

EXAMPLES = r'''
- name: Alice belongs to the Lyon tenant
  plakarkorp.plakar.member:
    organization: Lyon
    email: alice@example.com
    name: Alice
  register: alice

- name: Relay the one-time password when an account was just created
  ansible.builtin.debug:
    msg: "initial password: {{ alice.generated_password }}"
  when: alice.account_created | default(false)

- name: A service account for the nightly automation
  plakarkorp.plakar.member:
    organization: Lyon
    name: nightly-automation
    service: true

- name: Alice leaves
  plakarkorp.plakar.member:
    organization: Lyon
    email: alice@example.com
    state: absent
'''

RETURN = r'''
member:
  description: The member acted on (user_id, email, account, name, is_service).
  returned: when the membership exists or was created
  type: dict
account_created:
  description: Whether a brand-new account was registered for the address.
  returned: on creation
  type: bool
generated_password:
  description: The one-time must-change password the server minted for a
    brand-new account. Shown exactly once — relay it or lose it. C(null) when
    the address already had an account. A service account gets one too, but it
    is inert — an application user has no interactive login, and mints its API
    key in the Plakar UI.
  returned: on creation
  type: str
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)
from ansible_collections.plakarkorp.plakar.plugins.module_utils.orgs import (
    run_member_module)


def main():
    spec = argument_spec()
    spec.update(
        organization=dict(type='str'),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        email=dict(type='str'),
        name=dict(type='str'),
        service=dict(type='bool', default=False),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True,
                           required_one_of=[('email', 'name')])
    client = PlakarClient(module)
    try:
        run_member_module(module, client)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
