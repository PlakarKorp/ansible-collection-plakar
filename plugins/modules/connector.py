#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: connector
short_description: Manage Plakar source and destination connectors
version_added: 0.9.1
description:
  - Creates, updates and deletes source and destination connectors in the
    Plakar management API. For stores, use M(plakarkorp.plakar.store)
    instead.
  - Connectors are matched by name within the organization; the name is the
    playbook's key, so it must be unique per connector type.
  - Only the options the playbook sets are managed on update; anything else
    keeps its current server-side value.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
  - plakarkorp.plakar.plakar.secrets
options:
  name:
    description:
      - Name of the connector.
    type: str
    required: true
  state:
    description:
      - Whether the connector should exist.
    type: str
    default: present
    choices: [present, absent]
  type:
    description:
      - What the connector is used for.
    type: str
    required: true
    choices: [source, destination]
  protocol:
    description:
      - Protocol spoken to the resource, for example C(s3) or C(sftp).
      - Defaults to the integration name, which matches for the standard
        integrations; set it only when they differ.
    type: str
  integration:
    description:
      - Name of the installed integration backing the connector, for example
        C(s3) or C(sftp).
      - Required when creating; immutable afterwards. Naming another one for
        an existing connector fails the task.
    type: str
  resource:
    description:
      - URN or name of the inventory resource the connector attaches to.
      - Required when creating; immutable afterwards. A URN and a name for
        the same resource are the same resource, and naming another one for
        an existing connector fails the task.
      - A connector whose resource was deleted since, by hand or by a sync
        after it disappeared from the cloud, is left without one. The
        Control Plane then refuses any change to it but a new resource, which
        it takes in place.
    type: str
  fields:
    description:
      - Integration-specific configuration, as a mapping of field name to
        value.
      - To take a value from a secret provider instead, give a mapping with
        V(value), the path of the secret in the provider, and V(provider),
        the name of the secret provider as M(plakarkorp.plakar.secret_provider)
        declares it. V(provider_id) takes its id instead of its name.
      - On update, only the fields named here are compared and replaced;
        other existing fields are preserved.
    type: dict
  endpoints:
    description:
      - Endpoint names the connector reaches its resource through.
    type: list
    elements: str
  data_classes:
    description:
      - Data classes the connector carries.
      - Sources only. The Control Plane refuses them on a destination, and
        so does the module.
    type: list
    elements: str
  environment:
    description:
      - Environment label, for example C(production).
    type: str
  temperature:
    description:
      - Refused when set. The Control Plane only accepts a temperature on a
        store.
    type: str
'''

EXAMPLES = r'''
- name: SFTP source for the web tier
  plakarkorp.plakar.connector:
    name: Web tier
    type: source
    protocol: sftp
    integration: sftp
    resource: urn:res-grateful-cascade
    environment: production
    data_classes: [filesystem]
    fields:
      username: tunnel
      root: /home/tunnel/data
      port: 2222

- name: Retire it
  plakarkorp.plakar.connector:
    name: Web tier
    type: source
    state: absent
'''

RETURN = r'''
connector:
  description: The connector acted on (a summary; field values are not echoed).
  returned: when the connector exists or was created
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
from ansible_collections.plakarkorp.plakar.plugins.module_utils.connectors import (
    connector_options, run_connector_module)


def main():
    spec = argument_spec()
    spec.update(connector_options())
    spec.update(type=dict(type='str', required=True, choices=['source', 'destination']))
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)
    try:
        run_connector_module(module, client, module.params['type'])
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
