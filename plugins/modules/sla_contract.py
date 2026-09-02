#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: sla_contract
short_description: Bind a Plakar SLA template to a source
version_added: 0.1.0
description:
  - Creates and deletes SLA contracts — the binding that puts a template's
    protection policy in force for one source connector.
  - A contract is identified by its (template, source) pair; both are given
    by name and resolved within the organization.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  template:
    description:
      - Name of the SLA template.
    type: str
    required: true
  source:
    description:
      - Name of the source connector the template applies to.
    type: str
    required: true
  state:
    description:
      - Whether the binding should exist.
    type: str
    default: present
    choices: [present, absent]
'''

EXAMPLES = r'''
- name: The database source runs under the critical SLA
  plakarkorp.plakar.sla_contract:
    template: Critical SLA
    source: Production DB

- name: Release it
  plakarkorp.plakar.sla_contract:
    template: Critical SLA
    source: Production DB
    state: absent
'''

RETURN = r'''
contract:
  description: The contract acted on.
  returned: when the contract exists or was created
  type: dict
  contains:
    id:
      description: Contract id.
      type: str
    template_id:
      description: Template id.
      type: str
    source_id:
      description: Source connector id.
      type: str
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)


def main():
    spec = argument_spec()
    spec.update(
        template=dict(type='str', required=True),
        source=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)
    params = module.params

    try:
        template = client.find_sla_template(params['template'])
        if template is None and params['state'] == 'absent':
            module.exit_json(changed=False)
        if template is None:
            raise PlakarError('no SLA template named %r' % params['template'])

        if params['state'] == 'absent':
            source = client.find_connector('source', params['source'])
            if source is None:
                module.exit_json(changed=False)
        else:
            source = client.connector_by_name('source', params['source'])

        existing = [c for c in client.sla_contracts()
                    if c.get('template_id') == template['id']
                    and c.get('source_id') == source['id']]
        current = existing[0] if existing else None

        def summary(c):
            return {'id': c.get('id'), 'template_id': c.get('template_id'),
                    'source_id': c.get('source_id')}

        if params['state'] == 'absent':
            if current is None:
                module.exit_json(changed=False)
            if not module.check_mode:
                client.request('DELETE', client.sla_path('contracts/%s' % current['id']),
                               ok=(200, 204))
            module.exit_json(changed=True, contract=summary(current))

        if current is not None:
            module.exit_json(changed=False, contract=summary(current))
        if module.check_mode:
            module.exit_json(changed=True,
                             contract={'template_id': template['id'], 'source_id': source['id']})
        created = client.request('POST', client.sla_path('contracts'),
                                 body={'template_id': template['id'],
                                       'source_id': source['id']},
                                 ok=(200, 201))
        module.exit_json(changed=True, contract=summary(created))
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
