#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: schedule
short_description: Manage scheduled Plakar tasks
version_added: 0.10.0
description:
  - Creates, updates and deletes scheduled tasks — recurring backups, checks,
    syncs and prunes — in the Plakar management API.
  - The API does not persist a task's name, so a task is addressed by what it
    does instead - its type, its origin and target connectors, and its
    labels. Together those four options are the task's identity; changing any
    of them in the playbook manages a different task, it does not rename the
    existing one.
  - Consequently the module manages at most one task per (type, origin,
    target, labels) tuple. Several check tasks on one store are told apart by
    their labels, which is also how a check is scoped to the snapshots of one
    resource.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  name:
    description:
      - Display name sent when creating or updating the task.
      - The API does not store it, so it plays no part in matching; it is
        purely decorative.
    type: str
  description:
    description:
      - Description sent when creating or updating the task; decorative, like
        O(name).
    type: str
  state:
    description:
      - Whether the scheduled task should exist.
    type: str
    default: present
    choices: [present, absent]
  type:
    description:
      - The operation the schedule performs.
      - V(backup) reads its O(origin) source and writes to its O(target)
        store; V(sync) replicates its O(origin) store to its O(target) store;
        V(check) and V(prune) act on their O(origin) store and take no
        target.
    type: str
    required: true
    choices: [backup, check, sync, prune]
  origin:
    description:
      - Name of the origin connector; a source for V(backup), a store for
        every other type.
    type: str
    required: true
  target:
    description:
      - Name of the target store.
      - Required for V(backup) and V(sync); the other types take none.
    type: str
  labels:
    description:
      - Labels for the task. A backup tags its snapshots with them; a check
        or prune selects the snapshots carrying them.
      - Part of the task's identity (see the module description).
    type: list
    elements: str
    default: []
  ignores:
    description:
      - Path patterns a V(backup) excludes.
    type: list
    elements: str
  retention:
    description:
      - Retention buckets for a V(prune), as a mapping of bucket name
        (C(minute), C(per_minute), C(hour), C(per_hour), C(day), C(per_day),
        C(week), C(per_week), C(month), C(per_month), C(year), C(per_year))
        to a positive count.
    type: dict
  group_by:
    description:
      - Snapshot grouping for a V(prune)'s retention rules.
    type: str
  rules:
    description:
      - The recurrence rules of the schedule. At least one is required when
        the task exists.
    type: list
    elements: dict
    suboptions:
      periodicity:
        description:
          - Seconds between two runs.
        type: int
        required: true
      start:
        description:
          - ISO8601 time the rule starts at; unset starts it immediately.
        type: str
      jitter:
        description:
          - Random delay, in seconds, added to each run.
        type: int
      enabled:
        description:
          - Whether the rule fires.
        type: bool
        default: true
  enabled:
    description:
      - Whether the schedule as a whole fires.
    type: bool
    default: true
  priority:
    description:
      - Scheduling priority of the task's jobs.
    type: int
  concurrency:
    description:
      - How many jobs of this task may run at once.
    type: int
  miss_strategy:
    description:
      - What to do with runs missed while the scheduler was down.
    type: str
'''

EXAMPLES = r'''
- name: Back up web-01 every minute
  plakarkorp.plakar.schedule:
    name: web-01 backup
    type: backup
    origin: web-01 data
    target: Demo store
    labels: [host:web-01]
    rules:
      - periodicity: 60

- name: Verify web-01 snapshots every minute
  plakarkorp.plakar.schedule:
    name: web-01 restore test
    type: check
    origin: Demo store
    labels: [host:web-01]
    rules:
      - periodicity: 60

- name: Stop pruning the archive store
  plakarkorp.plakar.schedule:
    type: prune
    origin: Archive
    state: absent
'''

RETURN = r'''
task:
  description: The scheduled task acted on.
  returned: when the task exists or was created
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

# Same buckets the prune module validates; the API silently drops unknown
# config fields, so they are checked client-side here too.
RETENTION_BUCKETS = ('minute', 'per_minute', 'hour', 'per_hour', 'day',
                     'per_day', 'week', 'per_week', 'month', 'per_month',
                     'year', 'per_year')

# Which connector kind each side of a task resolves to. None forbids the side.
TASK_SHAPES = {
    'backup': ('source', 'store'),
    'sync': ('store', 'store'),
    'check': ('store', None),
    'prune': ('store', None),
}


def build_schedule(params):
    rules = []
    for r in params['rules'] or []:
        rule = {'enabled': r.get('enabled', True),
                'periodicity': r['periodicity']}
        if r.get('start') is not None:
            rule['start'] = r['start']
        if r.get('jitter') is not None:
            rule['jitter'] = r['jitter']
        rules.append(rule)
    schedule = {'enabled': params['enabled'], 'rules': rules}
    if params.get('priority') is not None:
        schedule['priority'] = params['priority']
    if params.get('concurrency') is not None:
        schedule['concurrency'] = params['concurrency']
    if params.get('miss_strategy'):
        schedule['miss_strategy'] = params['miss_strategy']
    return schedule


def build_config(module):
    params = module.params
    config = {}
    if params['labels']:
        config['labels'] = sorted(params['labels'])
    if params.get('ignores'):
        config['ignores'] = params['ignores']
    retention = params.get('retention')
    if retention:
        if params['type'] != 'prune':
            module.fail_json(msg='retention only applies to prune tasks')
        for bucket, count in retention.items():
            if bucket not in RETENTION_BUCKETS:
                module.fail_json(msg='unknown retention bucket %r (known: %s)'
                                     % (bucket, ', '.join(RETENTION_BUCKETS)))
            config[bucket] = int(count)
    if params.get('group_by'):
        if params['type'] != 'prune':
            module.fail_json(msg='group_by only applies to prune tasks')
        config['locate'] = {'group_by': params['group_by']}
    return config


def task_labels(task):
    """The labels of a stored task, whose config is polymorphic."""
    config = task.get('config') or {}
    return sorted(config.get('labels') or [])


def list_tasks(client):
    return client.paged('/api/v1/scheduling/scheduler/tasks')


def match_task(client, task_type, origin_id, target_id, labels):
    """The one task with this identity, None when absent."""
    matches = []
    for task in list_tasks(client):
        if task.get('type') != task_type:
            continue
        if ((task.get('origin') or {}).get('id')) != origin_id:
            continue
        if ((task.get('target') or {}).get('id') or None) != target_id:
            continue
        if task_labels(task) != sorted(labels):
            continue
        matches.append(task)
    if len(matches) > 1:
        raise PlakarError('%d %s tasks share origin, target and labels %r — '
                          'clean the duplicates up before managing them from '
                          'a playbook' % (len(matches), task_type, labels))
    return matches[0] if matches else None


def schedule_differs(module, current, wanted):
    """Compare the stored schedule to the wanted one, managed fields only."""
    diff = []
    if bool(current.get('enabled')) != wanted['enabled']:
        diff.append('enabled')
    for key in ('priority', 'concurrency'):
        if key in wanted and current.get(key) != wanted[key]:
            diff.append(key)
    if 'miss_strategy' in wanted and \
            (current.get('miss_strategy') or '') != wanted['miss_strategy']:
        diff.append('miss_strategy')

    def rule_view(rule):
        return (rule.get('periodicity'), rule.get('jitter') or 0,
                bool(rule.get('enabled')))

    current_rules = sorted(rule_view(r) for r in (current.get('rules') or []))
    wanted_rules = sorted(rule_view(r) for r in wanted['rules'])
    if current_rules != wanted_rules:
        diff.append('rules')
    return diff


def config_differs(module, task, config):
    """Compare the stored config to the wanted one, managed fields only."""
    diff = []
    current = task.get('config') or {}
    if module.params.get('ignores') is not None and \
            sorted(current.get('ignores') or []) != sorted(config.get('ignores') or []):
        diff.append('ignores')
    for bucket in RETENTION_BUCKETS:
        if bucket in config and current.get(bucket) != config[bucket]:
            diff.append('retention')
            break
    if 'locate' in config:
        current_group = (current.get('locate') or {}).get('group_by') or ''
        if current_group != config['locate']['group_by']:
            diff.append('group_by')
    return diff


def main():
    spec = argument_spec()
    spec.update(
        name=dict(type='str'),
        description=dict(type='str'),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        type=dict(type='str', required=True,
                  choices=sorted(TASK_SHAPES)),
        origin=dict(type='str', required=True),
        target=dict(type='str'),
        labels=dict(type='list', elements='str', default=[]),
        ignores=dict(type='list', elements='str'),
        retention=dict(type='dict'),
        group_by=dict(type='str'),
        rules=dict(type='list', elements='dict', options=dict(
            periodicity=dict(type='int', required=True),
            start=dict(type='str'),
            jitter=dict(type='int'),
            enabled=dict(type='bool', default=True),
        )),
        enabled=dict(type='bool', default=True),
        priority=dict(type='int'),
        concurrency=dict(type='int'),
        miss_strategy=dict(type='str'),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    params = module.params
    client = PlakarClient(module)

    task_type = params['type']
    origin_kind, target_kind = TASK_SHAPES[task_type]
    if params['target'] and target_kind is None:
        module.fail_json(msg='%s tasks take no target' % task_type)
    if not params['target'] and target_kind is not None:
        module.fail_json(msg='%s tasks require a target store' % task_type)

    try:
        # A task being removed may outlive its connectors; absence of the
        # origin then simply means there is nothing left to delete.
        if params['state'] == 'absent':
            origin = client.find_connector(origin_kind, params['origin'])
            if origin is None:
                module.exit_json(changed=False)
            target = None
            if target_kind is not None:
                target = client.find_connector(target_kind, params['target'])
                if target is None:
                    module.exit_json(changed=False)
        else:
            origin = client.connector_by_name(origin_kind, params['origin'])
            target = None
            if target_kind is not None:
                target = client.connector_by_name(target_kind, params['target'])
        target_id = target['id'] if target else None

        existing = match_task(client, task_type, origin['id'], target_id,
                              params['labels'])

        if params['state'] == 'absent':
            if existing is None:
                module.exit_json(changed=False)
            if not module.check_mode:
                client.request('DELETE',
                               '/api/v1/scheduling/scheduler/tasks/%s'
                               % existing['id'], ok=(200, 204))
            module.exit_json(changed=True, task=existing)

        if not params['rules']:
            module.fail_json(msg='at least one rule is required when the '
                                 'task is present')

        schedule = build_schedule(params)
        config = build_config(module)
        body = {
            'name': params['name'] or '%s %s' % (task_type, params['origin']),
            'description': params['description'] or '',
            'type': task_type,
            'origin': {'id': origin['id']},
            'schedule': schedule,
            'config': config,
        }
        if target_id:
            body['target'] = {'id': target_id}

        if existing is None:
            if module.check_mode:
                module.exit_json(changed=True, task=body)
            created = client.request('POST', '/api/v1/scheduling/scheduler/tasks',
                                     body=body, ok=(200, 201))
            module.exit_json(changed=True, task=created)

        diff_keys = schedule_differs(module, existing.get('schedule') or {},
                                     schedule)
        diff_keys += config_differs(module, existing, config)
        if not diff_keys:
            module.exit_json(changed=False, task=existing)
        if module.check_mode:
            module.exit_json(changed=True, task=existing, diff_keys=diff_keys)
        client.request('POST', '/api/v1/scheduling/scheduler/tasks/%s'
                       % existing['id'], body=body, ok=(200, 204))
        updated = match_task(client, task_type, origin['id'], target_id,
                             params['labels'])
        module.exit_json(changed=True, task=updated or existing,
                         diff_keys=diff_keys)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
