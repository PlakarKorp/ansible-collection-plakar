#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: secret_provider
short_description: Manage Plakar secret providers
version_added: 0.10.0
description:
  - Creates, updates and deletes secret providers in the Plakar management
    API. A secret provider is an external secret manager, such as Vault or
    Scaleway Secret Manager, that the fields of a store, a connector or an
    inventory can point into instead of holding a value.
  - Declaring one only records how to reach the secret manager. Plakar
    contacts it when a field that references it is resolved.
  - Secret providers are matched by name within the organization; the name
    is the playbook's key, so it must be unique.
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
      - Name of the secret provider.
    type: str
    required: true
  state:
    description:
      - Whether the secret provider should exist.
    type: str
    default: present
    choices: [present, absent]
  integration:
    description:
      - Name of the installed integration backing the secret provider, for
        example C(vault) or C(scaleway).
      - Required when creating; immutable afterwards.
    type: str
  protocol:
    description:
      - Protocol spoken to the secret manager.
      - Defaults to the one the integration declares for secret providers.
        Unlike a store's, it does not share the integration's name, C(vault)
        speaks C(vault-sm), so set it only when the integration declares
        several.
    type: str
  fields:
    description:
      - Integration-specific configuration, as a mapping of field name to
        plain value, for example C(url) and C(token) for C(vault).
      - The credential of a secret provider is the one secret that cannot
        come from a secret provider. Take it from Ansible Vault or from a
        lookup, not from the playbook's text.
      - On update, only the fields named here are compared and replaced;
        other existing fields are preserved.
    type: dict
'''

EXAMPLES = r'''
- name: Vault
  plakarkorp.plakar.secret_provider:
    name: Vault
    integration: vault
    fields:
      url: https://vault.example.com:8200
      token: "{{ vault_plakar_token }}"

- name: A store whose keys stay in Vault
  plakarkorp.plakar.store:
    name: Offsite S3
    integration: s3
    resource: Ample Sky
    fields:
      root: /backups
      passphrase:
        value: secret/prod/plakar#passphrase
        provider: Vault
      access_key:
        value: secret/prod/s3#access_key
        provider: Vault
      secret_access_key:
        value: secret/prod/s3#secret_key
        provider: Vault

- name: Rotate the token Plakar reaches Vault with
  plakarkorp.plakar.secret_provider:
    name: Vault
    update_secrets: always
    fields:
      token: "{{ vault_plakar_token }}"

- name: Retire it
  plakarkorp.plakar.secret_provider:
    name: Vault
    state: absent
'''

RETURN = r'''
secret_provider:
  description: The secret provider acted on (a summary; field values are not
    echoed). A field of a store, a connector or an inventory references it
    by its C(name) as C(provider), or by its C(id) as C(provider_id).
  returned: when the secret provider exists or was created
  type: dict
diff_keys:
  description: The option names whose values differed and drove the update.
  returned: on update
  type: list
  elements: str
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec, update_secrets_option)
from ansible_collections.plakarkorp.plakar.plugins.module_utils.secret_providers import (
    run_secret_provider_module)


def main():
    spec = argument_spec()
    spec.update(
        name=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        integration=dict(type='str'),
        protocol=dict(type='str'),
        fields=dict(type='dict', no_log=True),
    )
    spec.update(update_secrets_option())
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)
    try:
        run_secret_provider_module(module, client)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
