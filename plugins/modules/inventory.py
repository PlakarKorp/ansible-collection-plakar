#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: inventory
short_description: Manage Plakar inventories
version_added: 0.1.0
description:
  - Creates, updates and deletes inventories in the Plakar management API.
  - An inventory watches what a provider holds (AWS, Scaleway, GCP, OVH,
    VMware, Kubernetes) or, for the C(self-managed) type, holds resources a
    playbook declares itself with M(plakarkorp.plakar.inventory_resource).
  - Inventories are matched by name within the organization; the name is the
    playbook's key, so it must be unique. The type is immutable once created.
  - Only the configuration keys the playbook sets are managed on update;
    anything else keeps its current server-side value.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  name:
    description:
      - Name of the inventory.
    type: str
    required: true
  state:
    description:
      - Whether the inventory should exist.
    type: str
    default: present
    choices: [present, absent]
  type:
    description:
      - Provider backing the inventory.
      - Required when creating; immutable afterwards.
    type: str
    choices: [aws, gcp, k8s, ovh, scaleway, self-managed, vmware]
  configuration:
    description:
      - Provider-specific configuration, as a flat mapping of field name to
        value. A value may also be a mapping with V(value) and an optional
        V(provider_id) naming a secret provider.
      - "Keys per type — C(aws): C(credentials_type) (C(iam) or
        C(access_key)), C(region), C(access_key), C(secret_access_key);
        C(scaleway): C(scw_project_id), C(scw_access_key), C(scw_secret_key);
        C(gcp): C(gcp_project_id), C(gcp_service_account_json);
        C(ovh): C(application_key), C(application_secret), C(consumer_key),
        C(endpoint); C(k8s): C(k8s_kubeconf); C(vmware): C(vsphere_server),
        C(vsphere_username), C(vsphere_password), C(vsphere_tls_skip_verify),
        C(vsphere_tls_ca_bundle)."
      - The C(self-managed) type takes no configuration.
    type: dict
'''

EXAMPLES = r'''
- name: Watch a Scaleway project
  plakarkorp.plakar.inventory:
    name: Production Scaleway
    type: scaleway
    configuration:
      scw_project_id: 11111111-2222-3333-4444-555555555555
      scw_access_key: SCWXXXXXXXXXXXXXXXXX
      scw_secret_key: "{{ vault_scw_secret_key }}"

- name: An inventory of hand-declared machines
  plakarkorp.plakar.inventory:
    name: Datacenter racks
    type: self-managed

- name: Retire it
  plakarkorp.plakar.inventory:
    name: Datacenter racks
    state: absent
'''

RETURN = r'''
inventory:
  description: The inventory acted on (a summary; configuration values are not echoed).
  returned: when the inventory exists or was created
  type: dict
diff_keys:
  description: The configuration keys whose values differed and drove the update.
  returned: on update
  type: list
  elements: str
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)
from ansible_collections.plakarkorp.plakar.plugins.module_utils.inventories import (
    inventory_types, run_inventory_module)


def main():
    spec = argument_spec()
    spec.update(
        name=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        type=dict(type='str', choices=inventory_types()),
        configuration=dict(type='dict', no_log=True),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)
    try:
        run_inventory_module(module, client)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
