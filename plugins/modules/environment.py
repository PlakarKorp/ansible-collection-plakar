#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: environment
short_description: Manage the environments of a Plakar organization
version_added: 0.10.0
description:
  - Adds an environment to an organization, or removes it. Environments are
    the names a store or a connector can carry as its C(environment), and
    the Classification page lists them.
  - A new organization comes with C(integration), C(production), C(staging)
    and C(testing).
  - Names are kept exactly as written, case and spaces included, so C(Prod)
    and C(prod) are two environments. A name is its own identity; there is
    nothing to update.
notes:
  - Call it by its full name, C(plakarkorp.plakar.environment). The short
    name is also a task keyword, which Ansible would read instead.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  name:
    description:
      - Name of the environment.
    type: str
    required: true
  state:
    description:
      - Whether the environment should exist.
      - V(absent) removes the name for the whole organization.
    type: str
    default: present
    choices: [present, absent]
'''

EXAMPLES = r'''
- name: A pre-production environment
  plakarkorp.plakar.environment:
    name: preprod

- name: Label a store with it
  plakarkorp.plakar.store:
    name: Offsite S3
    environment: preprod

- name: The organization has no testing environment
  plakarkorp.plakar.environment:
    name: testing
    state: absent
'''

RETURN = r'''
environment:
  description: The environment acted on, with its C(name).
  returned: when the environment exists, or was removed
  type: dict
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.classification import (
    classification_options, run_classification_module)
from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)


def main():
    spec = argument_spec()
    spec.update(classification_options())
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)
    try:
        run_classification_module(module, client, 'environment')
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
