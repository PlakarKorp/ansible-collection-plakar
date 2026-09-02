#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: repository
short_description: Manage Plakar backup repositories
version_added: 0.1.0
description:
  - Creates, updates and deletes backup repositories — store connectors — in
    the Plakar management API, initializing the underlying kloset store on
    creation.
  - Repositories are matched by name within the organization; the name is the
    playbook's key, so it must be unique among stores.
  - Only the options the playbook sets are managed on update; anything else
    keeps its current server-side value.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  name:
    description:
      - Name of the repository.
    type: str
    required: true
  state:
    description:
      - Whether the repository should exist.
      - V(absent) removes the store connector from Plakar; the data in the
        underlying storage is not touched.
    type: str
    default: present
    choices: [present, absent]
  protocol:
    description:
      - Protocol of the integration, for example C(s3) or C(sftp).
      - Required when creating.
    type: str
  integration:
    description:
      - Name of the installed integration backing the repository.
      - Required when creating.
    type: str
  resource:
    description:
      - URN or name of the inventory resource the repository attaches to.
      - Required when creating.
    type: str
  fields:
    description:
      - Integration-specific configuration, as a mapping of field name to
        value. A value may also be a mapping with V(value) and an optional
        V(provider_id) naming a secret provider.
      - On update, only the fields named here are compared and replaced;
        other existing fields are preserved.
    type: dict
  endpoints:
    description:
      - Endpoint names the repository reaches its resource through.
    type: list
    elements: str
  data_classes:
    description:
      - Data classes the repository accepts.
    type: list
    elements: str
  environment:
    description:
      - Environment label, for example C(production).
    type: str
  temperature:
    description:
      - Storage temperature.
    type: str
  initialize:
    description:
      - Whether to initialize the kloset store right after creating the
        connector. Initialization only happens on creation, never on update.
    type: bool
    default: true
  compression:
    description:
      - Compression for the kloset store at initialization. Unset keeps
        kloset's own default.
    type: str
    choices: [GZIP, LZ4, ZSTD]
'''

EXAMPLES = r'''
- name: S3 repository
  plakarkorp.plakar.repository:
    name: Offsite S3
    protocol: s3
    integration: s3
    resource: Ample Sky
    environment: production
    compression: ZSTD
    fields:
      passphrase: "{{ vault_repo_passphrase }}"
      access_key: "{{ vault_s3_access_key }}"
      secret_access_key: "{{ vault_s3_secret_key }}"
      root: /backups
'''

RETURN = r'''
connector:
  description: The store connector acted on (a summary; field values are not
    echoed). Carries C(initialized) when the module created it.
  returned: when the repository exists or was created
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
    spec.update(
        initialize=dict(type='bool', default=True),
        compression=dict(type='str', choices=['GZIP', 'LZ4', 'ZSTD']),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)
    try:
        run_connector_module(module, client, 'store', repository=True)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
