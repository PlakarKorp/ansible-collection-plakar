#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: data_class
short_description: Manage the data classes of a Plakar organization
version_added: 0.9.4
description:
  - Adds a data class to an organization, or removes it. Data classes are
    the names a source connector can carry in its C(data_classes), and the
    Classification page lists them.
  - A new organization comes with C(personal_data),
    C(sensitive_personal_data), C(health_records), C(cardholder_data),
    C(financial_records), C(employee_records), C(audit_logs),
    C(intellectual_property), C(business_data) and C(system_state).
  - Names are kept exactly as written, case and spaces included, so
    C(Payroll) and C(payroll) are two data classes. A name is its own
    identity; there is nothing to update.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  name:
    description:
      - Name of the data class.
    type: str
    required: true
  state:
    description:
      - Whether the data class should exist.
      - V(absent) removes the name for the whole organization.
    type: str
    default: present
    choices: [present, absent]
'''

EXAMPLES = r'''
- name: A data class of our own
  plakarkorp.plakar.data_class:
    name: payroll

- name: A source that carries it
  plakarkorp.plakar.connector:
    name: HR database
    type: source
    data_classes: [payroll, employee_records]

- name: The organization holds no cardholder data
  plakarkorp.plakar.data_class:
    name: cardholder_data
    state: absent
'''

RETURN = r'''
data_class:
  description: The data class acted on, with its C(name).
  returned: when the data class exists, or was removed
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
        run_classification_module(module, client, 'data_class')
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
