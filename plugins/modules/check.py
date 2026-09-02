#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: check
short_description: Verify the integrity of Plakar snapshots
version_added: 0.1.0
description:
  - Triggers an on-demand integrity check of the snapshots held in a store,
    through the Plakar management API.
  - The store is addressed by name and resolved within the organization at
    run time. Without O(snapshot_id) the whole store is checked.
  - The run is asynchronous server-side. By default the module polls until the
    job stops and fails unless it succeeded — a failed check means the data
    did not verify.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
  - plakarkorp.plakar.plakar.action
options:
  store:
    description:
      - Name of the store whose snapshots to verify.
    type: str
    required: true
  snapshot_id:
    description:
      - Check only this snapshot.
    type: str
  labels:
    description:
      - Only check snapshots carrying these labels.
    type: list
    elements: str
'''

EXAMPLES = r'''
- name: Weekly integrity check of the offsite store
  plakarkorp.plakar.check:
    store: Offsite S3
    wait_timeout: 3600

- name: Verify one snapshot before restoring it
  plakarkorp.plakar.check:
    store: S3 Store
    snapshot_id: "{{ snapshot_to_restore }}"
'''

RETURN = r'''
at_id:
  description: Identifier of the one-shot run (the scheduler's C(at) entry).
  returned: always (except check mode)
  type: str
job:
  description: The job the run materialized into. Only present once the
    scheduler picked the run up — with O(wait=false) it may be absent.
  returned: when available
  type: dict
  contains:
    id:
      description: Job id, usable with M(plakarkorp.plakar.job_info).
      type: str
    status:
      description: One of C(queued), C(running), C(canceled), C(succeeded), C(failed).
      type: str
    started_at:
      description: When the job started, if it did.
      type: str
    stopped_at:
      description: When the job stopped, if it did.
      type: str
log:
  description: Plain-text job log, fetched when the job did not succeed.
  returned: on job failure
  type: str
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec, run_wait_options)


def main():
    spec = argument_spec()
    spec.update(run_wait_options())
    spec.update(
        store=dict(type='str', required=True),
        snapshot_id=dict(type='str', required=False),
        labels=dict(type='list', elements='str', required=False),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)

    try:
        store = client.connector_by_name('store', module.params['store'])

        if module.check_mode:
            module.exit_json(changed=True, store_id=store['id'])

        config = {}
        if module.params.get('labels'):
            config['labels'] = module.params['labels']
        if module.params.get('snapshot_id'):
            config['snapshot_id'] = module.params['snapshot_id']

        at_id = client.run_task('check', store['id'],
                                config=config or None,
                                edge_tags=module.params.get('edge_tags'))

        if not module.params['wait']:
            job = client.at_status(at_id)
            module.exit_json(changed=True, at_id=at_id, **({'job': job} if job else {}))

        job = client.wait_at(at_id, timeout=module.params['wait_timeout'])
        if job['status'] != 'succeeded':
            log = ''
            try:
                log = client.job_log(job['id'])
            except PlakarError:
                pass
            module.fail_json(msg='check ended %s' % job['status'],
                             at_id=at_id, job=job, log=log)
        module.exit_json(changed=True, at_id=at_id, job=job)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
