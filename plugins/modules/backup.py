#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: backup
short_description: Trigger a Plakar backup
version_added: 0.9.1
description:
  - Triggers an on-demand backup of a source connector into a store, through
    the Plakar management API.
  - Connectors are addressed by name; names are resolved within the
    organization at run time.
  - The run is asynchronous server-side. By default the module polls until the
    job stops and fails unless it succeeded.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
  - plakarkorp.plakar.plakar.action
options:
  source:
    description:
      - Name of the source connector to back up.
    type: str
    required: true
  store:
    description:
      - Name of the store connector to back up into.
    type: str
    required: true
  labels:
    description:
      - Labels to attach to the resulting snapshot.
    type: list
    elements: str
  ignores:
    description:
      - Path patterns to exclude from the backup.
    type: list
    elements: str
'''

EXAMPLES = r'''
- name: Nightly database backup
  plakarkorp.plakar.backup:
    api_url: https://plakar.example.com
    api_key: "{{ plakar_api_key }}"
    source: Production DB
    store: S3 Store
    labels: [nightly, database]

- name: Fire and forget, check later
  plakarkorp.plakar.backup:
    source: Production DB
    store: S3 Store
    wait: false
  register: run

- name: Poll it later
  plakarkorp.plakar.job_info:
    at_id: "{{ run.at_id }}"
  register: info
  until: info.jobs | length > 0 and info.jobs[0].stopped_at is not none
  retries: 60
  delay: 10
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
        source=dict(type='str', required=True),
        store=dict(type='str', required=True),
        labels=dict(type='list', elements='str', required=False),
        ignores=dict(type='list', elements='str', required=False),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = PlakarClient(module)

    try:
        source = client.connector_by_name('source', module.params['source'])
        store = client.connector_by_name('store', module.params['store'])

        if module.check_mode:
            module.exit_json(changed=True, source_id=source['id'], store_id=store['id'])

        config = {}
        if module.params.get('labels'):
            config['labels'] = module.params['labels']
        if module.params.get('ignores'):
            config['ignores'] = module.params['ignores']

        at_id = client.run_task('backup', source['id'], store['id'],
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
            module.fail_json(msg='backup ended %s' % job['status'],
                             at_id=at_id, job=job, log=log)
        module.exit_json(changed=True, at_id=at_id, job=job)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


if __name__ == '__main__':
    main()
