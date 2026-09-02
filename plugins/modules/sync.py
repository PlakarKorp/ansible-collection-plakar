#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: sync
short_description: Sync snapshots between Plakar stores
version_added: 0.1.0
description:
  - Triggers an on-demand synchronization of snapshots from one store into
    another — offsite replication, hot-to-cold tiering — through the Plakar
    management API.
  - Stores are addressed by name; names are resolved within the organization
    at run time.
  - The run is asynchronous server-side. By default the module polls until the
    job stops and fails unless it succeeded.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
  - plakarkorp.plakar.plakar.action
options:
  store:
    description:
      - Name of the store holding the snapshots to sync.
    type: str
    required: true
  to_store:
    description:
      - Name of the store to sync the snapshots into.
    type: str
    required: true
  labels:
    description:
      - Only sync snapshots carrying these labels.
    type: list
    elements: str
'''

EXAMPLES = r'''
- name: Replicate the hot store offsite
  plakarkorp.plakar.sync:
    store: Hot S3
    to_store: Offsite S3

- name: Tier only the nightly snapshots to cold storage
  plakarkorp.plakar.sync:
    store: Hot S3
    to_store: Cold S3
    labels: [nightly]
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
        to_store=dict(type='str', required=True),
        labels=dict(type='list', elements='str', required=False),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)

    try:
        origin = client.connector_by_name('store', module.params['store'])
        target = client.connector_by_name('store', module.params['to_store'])

        if module.check_mode:
            module.exit_json(changed=True, store_id=origin['id'],
                             to_store_id=target['id'])

        config = {}
        if module.params.get('labels'):
            config['labels'] = module.params['labels']

        at_id = client.run_task('sync', origin['id'], target['id'],
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
            module.fail_json(msg='sync ended %s' % job['status'],
                             at_id=at_id, job=job, log=log)
        module.exit_json(changed=True, at_id=at_id, job=job)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
