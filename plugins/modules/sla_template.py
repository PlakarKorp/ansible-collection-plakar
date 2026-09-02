#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: sla_template
short_description: Manage Plakar SLA templates
version_added: 0.1.0
description:
  - Creates, updates and deletes SLA templates — the policies that say how
    often data must be protected and how long snapshots are retained.
  - Templates are matched by name within the organization; the name is the
    playbook's key.
  - Only the options the playbook sets are compared and patched on update;
    anything else keeps its current server-side value.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  name:
    description:
      - Name of the template.
    type: str
    required: true
  state:
    description:
      - Whether the template should exist.
    type: str
    default: present
    choices: [present, absent]
  environment:
    description:
      - Environment the template matches resources in, for example
        C(production).
    type: str
  data_classes:
    description:
      - Data classes the template matches.
    type: list
    elements: str
  tags:
    description:
      - Tags the template matches resources by.
    type: list
    elements: str
  temporalities:
    description:
      - Protection cadence and retention per time unit, as a mapping of unit
        (C(day), C(week), C(month), ...) to its constraint — V(frequency),
        V(retention), and the store snapshots land in, named by V(store)
        (resolved to its id) or given directly as V(store_id).
      - Compared and replaced as a whole when set.
    type: dict
  drills:
    description:
      - Drill constraints, passed through to the API as given.
      - Compared and replaced as a whole when set.
    type: list
    elements: dict
'''

EXAMPLES = r'''
- name: Critical protection policy
  plakarkorp.plakar.sla_template:
    name: Critical SLA
    environment: production
    data_classes: [database]
    temporalities:
      day:
        frequency: 4
        retention: 10
        store: S3 Store
      week:
        frequency: 1
        retention: 6
        store: S3 Store

- name: Drop it
  plakarkorp.plakar.sla_template:
    name: Critical SLA
    state: absent
'''

RETURN = r'''
template:
  description: The template acted on.
  returned: when the template exists or was created
  type: dict
  contains:
    id:
      description: Template id.
      type: str
    name:
      description: Template name.
      type: str
diff_keys:
  description: The option names whose values differed and drove the update.
  returned: on update
  type: list
  elements: str
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)

MANAGED = ('environment', 'data_classes', 'tags', 'temporalities', 'drills')


def _resolve_temporalities(client, raw):
    """Playbook shape -> API shape: 'store' names become store_id."""
    out = {}
    for unit, constraint in (raw or {}).items():
        c = dict(constraint)
        store = c.pop('store', None)
        if store and not c.get('store_id'):
            c['store_id'] = client.connector_by_name('store', store)['id']
        out[unit] = c
    return out


# The constraint keys a playbook can manage; server-side noise (id, created_at,
# updated_at) never participates in the comparison.
TEMPORALITY_KEYS = ('frequency', 'retention', 'store_id', 'start_time',
                    'storage_tier', 'replicas')


def _temporalities_differ(desired, current):
    current = current or {}
    if sorted(desired) != sorted(current):
        return True
    for unit, want in desired.items():
        have = current.get(unit) or {}
        for key in TEMPORALITY_KEYS:
            if key in want and want[key] != have.get(key):
                return True
    return False


def _normalized(key, value):
    if value is None:
        return None
    if key in ('data_classes', 'tags'):
        return sorted(value)
    return value


def main():
    spec = argument_spec()
    spec.update(
        name=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        environment=dict(type='str'),
        data_classes=dict(type='list', elements='str'),
        tags=dict(type='list', elements='str'),
        temporalities=dict(type='dict'),
        drills=dict(type='list', elements='dict'),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)
    params = module.params

    try:
        current = client.find_sla_template(params['name'])
        temporalities = None
        if params.get('temporalities') is not None:
            temporalities = _resolve_temporalities(client, params['temporalities'])

        if params['state'] == 'absent':
            if current is None:
                module.exit_json(changed=False)
            if not module.check_mode:
                client.request('DELETE', client.sla_path('templates/%s' % current['id']),
                               ok=(200, 204))
            module.exit_json(changed=True,
                             template={'id': current['id'], 'name': current['name']})

        if current is None:
            body = {'name': params['name']}
            for key in MANAGED:
                if key == 'temporalities':
                    if temporalities is not None:
                        body['temporalities'] = temporalities
                elif params.get(key) is not None:
                    body[key] = params[key]
            if module.check_mode:
                module.exit_json(changed=True, template={'name': params['name']})
            created = client.request('POST', client.sla_path('templates'),
                                     body=body, ok=(200, 201))
            module.exit_json(changed=True,
                             template={'id': created.get('id'), 'name': params['name']})

        changes = {}
        for key in MANAGED:
            if key == 'temporalities':
                if temporalities is not None and _temporalities_differ(
                        temporalities, current.get('temporalities')):
                    changes['temporalities'] = temporalities
                continue
            want = params.get(key)
            if want is None:
                continue
            if _normalized(key, want) != _normalized(key, current.get(key)):
                changes[key] = want

        summary = {'id': current['id'], 'name': current['name']}
        if not changes:
            module.exit_json(changed=False, template=summary)
        if module.check_mode:
            module.exit_json(changed=True, template=summary, diff_keys=sorted(changes))

        client.request('PATCH', client.sla_path('templates/%s' % current['id']),
                       body=changes)
        module.exit_json(changed=True, template=summary, diff_keys=sorted(changes))
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
