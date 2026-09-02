#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: prune
short_description: Prune snapshots from a Plakar store by retention rule
version_added: 0.1.0
description:
  - Applies a retention rule to a store's snapshots and deletes what falls
    outside it, through the Plakar management API. Snapshots under legal hold
    are never deleted and are reported separately.
  - In check mode nothing is deleted — the API's prune preview reports what
    would be deleted, kept and held.
  - The module is C(changed) only when snapshots were actually deleted (or,
    in check mode, would be).
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  store:
    description:
      - Name of the store to prune.
    type: str
    required: true
  retention:
    description:
      - The retention rule, as a mapping of bucket options — C(minute),
        C(hour), C(day), C(week), C(month), C(year) say how many recent
        buckets of that unit to keep, and C(per_minute), C(per_hour),
        C(per_day), C(per_week), C(per_month), C(per_year) how many snapshots
        to keep in each.
      - "For example V({day: 7, per_day: 1, month: 12, per_month: 1}) keeps
        one snapshot a day for a week and one a month for a year."
    type: dict
    required: true
  labels:
    description:
      - Only consider snapshots carrying these labels.
    type: list
    elements: str
  wait:
    description:
      - Whether to wait for the deletion job to finish when there is
        something to delete.
    type: bool
    default: true
  wait_timeout:
    description:
      - Seconds to wait for the deletion job before failing.
    type: int
    default: 600
'''

EXAMPLES = r'''
- name: Keep a daily snapshot for a week and a monthly one for a year
  plakarkorp.plakar.prune:
    store: S3 Store
    retention:
      day: 7
      per_day: 1
      month: 12
      per_month: 1

- name: See what a tighter rule would delete, without deleting
  plakarkorp.plakar.prune:
    store: S3 Store
    retention:
      day: 3
      per_day: 1
  check_mode: true
  register: preview
'''

RETURN = r'''
deleted:
  description: Snapshot ids the run deleted (in check mode, would delete).
  returned: always
  type: list
  elements: str
kept:
  description: Snapshot ids the rule keeps. Only the preview reports this.
  returned: in check mode
  type: list
  elements: str
held:
  description: Snapshot ids excluded because they are under legal hold.
  returned: always
  type: list
  elements: str
at_id:
  description: Identifier of the deletion run, when something was deleted.
  returned: when a deletion ran
  type: str
job:
  description: The deletion job, when something was deleted and O(wait=true).
  returned: when a deletion ran and was waited on
  type: dict
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)

RETENTION_KEYS = ('minute', 'per_minute', 'hour', 'per_hour', 'day', 'per_day',
                  'week', 'per_week', 'month', 'per_month', 'year', 'per_year')


def main():
    spec = argument_spec()
    spec.update(
        store=dict(type='str', required=True),
        retention=dict(type='dict', required=True),
        labels=dict(type='list', elements='str', required=False),
        wait=dict(type='bool', default=True),
        wait_timeout=dict(type='int', default=600),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)
    params = module.params

    # The API ignores unknown config fields, so a typo here would silently
    # prune under a different rule than the playbook wrote. Refuse instead.
    unknown = sorted(set(params['retention']) - set(RETENTION_KEYS))
    if unknown:
        module.fail_json(msg='unknown retention option(s): %s — valid: %s'
                             % (', '.join(unknown), ', '.join(RETENTION_KEYS)))

    body = {k: int(v) for k, v in params['retention'].items()}
    if params.get('labels'):
        body['labels'] = params['labels']

    try:
        store = client.connector_by_name('store', params['store'])

        if module.check_mode:
            res = client.request(
                'POST', '/api/v1/snapshots/store/%s/prune/preview' % store['id'],
                body=body)
            would = res.get('would_delete') or []
            module.exit_json(changed=bool(would), deleted=would,
                             kept=res.get('would_keep') or [],
                             held=res.get('held') or [])

        res = client.request(
            'POST', '/api/v1/snapshots/store/%s/prune/run' % store['id'],
            body=body)
        deleted = res.get('deleted') or []
        held = res.get('held') or []
        at_id = res.get('at_id')

        result = dict(changed=bool(deleted), deleted=deleted, held=held)
        if at_id:
            result['at_id'] = at_id
            if params['wait']:
                job = client.wait_at(at_id, timeout=params['wait_timeout'])
                if job['status'] != 'succeeded':
                    log = ''
                    try:
                        log = client.job_log(job['id'])
                    except PlakarError:
                        pass
                    module.fail_json(msg='prune deletion ended %s' % job['status'],
                                     log=log, **result)
                result['job'] = job
        module.exit_json(**result)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
