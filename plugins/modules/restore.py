#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: restore
short_description: Trigger a Plakar restore
version_added: 0.9.1
description:
  - Triggers an on-demand restore of a snapshot from a store onto a
    destination connector, through the Plakar management API.
  - Connectors are addressed by name. When no O(snapshot_id) is given, the
    newest snapshot in the store is restored.
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
      - Name of the store connector holding the snapshot.
    type: str
    required: true
  destination:
    description:
      - Name of the destination connector to restore onto.
    type: str
    required: true
  snapshot_id:
    description:
      - Identifier of the snapshot to restore.
      - When omitted, the newest snapshot in the store (by creation time) is
        restored.
    type: str
'''

EXAMPLES = r'''
- name: Restore the latest snapshot
  plakarkorp.plakar.restore:
    api_url: https://plakar.example.com
    api_key: "{{ plakar_api_key }}"
    store: S3 Store
    destination: Recovery target

- name: Restore a specific snapshot
  plakarkorp.plakar.restore:
    store: S3 Store
    destination: Recovery target
    snapshot_id: d3f1286e79df77637224188ccb5ad9dd3bb1fb5df353fcf7822222cce9eb7c3c
'''

RETURN = r'''
at_id:
  description: Identifier of the one-shot run (the scheduler's C(at) entry).
  returned: always (except check mode)
  type: str
snapshot_id:
  description: The snapshot that was restored.
  returned: always
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
        destination=dict(type='str', required=True),
        snapshot_id=dict(type='str', required=False),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)

    try:
        store = client.connector_by_name('store', module.params['store'])
        destination = client.connector_by_name('destination', module.params['destination'])

        snapshot_id = module.params.get('snapshot_id')
        if not snapshot_id:
            snapshot_id = client.latest_snapshot(store['id'])['snapshot_id']

        if module.check_mode:
            module.exit_json(changed=True, store_id=store['id'],
                             destination_id=destination['id'], snapshot_id=snapshot_id)

        at_id = client.run_task('restore', store['id'], destination['id'],
                                config={'snapshot_id': snapshot_id},
                                edge_tags=module.params.get('edge_tags'))

        if not module.params['wait']:
            job = client.at_status(at_id)
            module.exit_json(changed=True, at_id=at_id, snapshot_id=snapshot_id,
                             **({'job': job} if job else {}))

        job = client.wait_at(at_id, timeout=module.params['wait_timeout'])
        if job['status'] != 'succeeded':
            log = ''
            try:
                log = client.job_log(job['id'])
            except PlakarError:
                pass
            module.fail_json(msg='restore ended %s' % job['status'],
                             at_id=at_id, job=job, snapshot_id=snapshot_id, log=log)
        module.exit_json(changed=True, at_id=at_id, snapshot_id=snapshot_id, job=job)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
