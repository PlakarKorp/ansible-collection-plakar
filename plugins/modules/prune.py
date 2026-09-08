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
version_added: 0.9.1
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
  tags:
    description:
      - Only consider snapshots carrying these tags.
    type: list
    elements: str
  group_by:
    description:
      - Partition the matched snapshots before applying the rule, so retention
        is honored per group instead of across the whole store — for example
        V(dataset) keeps the rule per source instead of globally.
    type: str
    choices: [name, category, environment, perimeter, job, dataset, data-class, tag, origin, type, root]
  filters:
    description:
      - Further narrowing, passed to the API's locate filters — a mapping of
        C(ignore_tags), C(before), C(since), C(name), C(category),
        C(environment), C(perimeter), C(job), C(dataset), C(latest), C(ids),
        C(types), C(origins), C(roots), C(data_classes).
      - O(tags) is shorthand for C(filters.tags); both may be set and merge.
    type: dict
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

- name: Retention per source rather than across the whole store
  plakarkorp.plakar.prune:
    store: S3 Store
    retention:
      year: 2
      per_year: 2
    group_by: dataset

- name: Only the nightly snapshots, and see what would go, without deleting
  plakarkorp.plakar.prune:
    store: S3 Store
    retention:
      day: 3
      per_day: 1
    tags: [nightly]
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
floored:
  description: Snapshot ids the rule would delete but the organization's
    retention floor keeps anyway.
  returned: always
  type: list
  elements: str
at_ids:
  description: Identifiers of the deletion runs, when something was deleted.
    A long delete list may be split over several runs.
  returned: when a deletion ran
  type: list
  elements: str
jobs:
  description: The deletion jobs, when something was deleted and O(wait=true).
  returned: when a deletion ran and was waited on
  type: list
  elements: dict
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)

RETENTION_KEYS = ('minute', 'per_minute', 'hour', 'per_hour', 'day', 'per_day',
                  'week', 'per_week', 'month', 'per_month', 'year', 'per_year')

FILTER_KEYS = ('tags', 'ignore_tags', 'before', 'since', 'name', 'category',
               'environment', 'perimeter', 'job', 'dataset', 'latest', 'ids',
               'types', 'origins', 'roots', 'data_classes')


def main():
    spec = argument_spec()
    spec.update(
        store=dict(type='str', required=True),
        retention=dict(type='dict', required=True),
        tags=dict(type='list', elements='str', required=False),
        group_by=dict(type='str', required=False,
                      choices=['name', 'category', 'environment', 'perimeter',
                               'job', 'dataset', 'data-class', 'tag', 'origin',
                               'type', 'root']),
        filters=dict(type='dict', required=False),
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
    filters = dict(params.get('filters') or {})
    unknown = sorted(set(filters) - set(FILTER_KEYS))
    if unknown:
        module.fail_json(msg='unknown filter(s): %s — valid: %s'
                             % (', '.join(unknown), ', '.join(FILTER_KEYS)))
    if params.get('tags'):
        filters['tags'] = sorted(set(filters.get('tags') or []) | set(params['tags']))

    body = {k: int(v) for k, v in params['retention'].items()}
    locate = {}
    if filters:
        locate['filters'] = filters
    if params.get('group_by'):
        locate['group_by'] = params['group_by']
    if locate:
        body['locate'] = locate

    try:
        store = client.connector_by_name('store', params['store'])

        if module.check_mode:
            res = client.request(
                'POST', '/api/v1/snapshots/store/%s/prune/preview' % store['id'],
                body=body)
            would = res.get('would_delete') or []
            module.exit_json(changed=bool(would), deleted=would,
                             kept=res.get('would_keep') or [],
                             held=res.get('held') or [],
                             floored=res.get('floored') or [])

        res = client.request(
            'POST', '/api/v1/snapshots/store/%s/prune/run' % store['id'],
            body=body)
        deleted = res.get('deleted') or []
        held = res.get('held') or []
        # A long delete list may be split over several runs (at_ids, plakman
        # >= v0.14.0); older servers answered a single at_id.
        at_ids = res.get('at_ids') or ([res['at_id']] if res.get('at_id') else [])

        result = dict(changed=bool(deleted), deleted=deleted, held=held,
                      floored=res.get('floored') or [])
        if at_ids:
            result['at_ids'] = at_ids
            if params['wait']:
                jobs = []
                for at_id in at_ids:
                    job = client.wait_at(at_id, timeout=params['wait_timeout'])
                    jobs.append(job)
                    if job['status'] != 'succeeded':
                        log = ''
                        try:
                            log = client.job_log(job['id'])
                        except PlakarError:
                            pass
                        module.fail_json(msg='prune deletion ended %s' % job['status'],
                                         log=log, jobs=jobs, **result)
                result['jobs'] = jobs
        module.exit_json(**result)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
