#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: job_info
short_description: Query Plakar job state
version_added: 0.1.0
description:
  - Reads job state from the Plakar management API, either one job by id or a
    filtered list.
  - Never changes anything.
author:
  - PlakarKorp (@PlakarKorp)
extends_documentation_fragment:
  - plakarkorp.plakar.plakar
options:
  job_id:
    description:
      - Return exactly this job. Mutually exclusive with the list filters.
    type: str
  at_id:
    description:
      - Return the job of this one-shot run, as returned in C(at_id) by
        M(plakarkorp.plakar.backup) and M(plakarkorp.plakar.restore).
      - While the scheduler has not yet materialized the run into a job, the
        module returns an empty RV(jobs) list — poll with C(until).
    type: str
  task_type:
    description:
      - Only jobs of this task type.
    type: str
    choices: [backup, restore, sync, check, prune, rm, maintenance]
  status:
    description:
      - Only jobs in this state.
    type: str
    choices: [queued, running, canceled, succeeded, failed]
  limit:
    description:
      - Maximum number of jobs to return.
    type: int
    default: 50
  offset:
    description:
      - Pagination offset.
    type: int
    default: 0
  include_log:
    description:
      - Also fetch each returned job's plain-text log. Meant for a single job
        or a narrow filter; logs are fetched one request per job.
    type: bool
    default: false
'''

EXAMPLES = r'''
- name: Last failed backups
  plakarkorp.plakar.job_info:
    task_type: backup
    status: failed
    limit: 10
  register: failed

- name: One job, with its log
  plakarkorp.plakar.job_info:
    job_id: "{{ run.job.id }}"
    include_log: true
'''

RETURN = r'''
jobs:
  description: The matching jobs, newest first (server ordering).
  returned: always
  type: list
  elements: dict
  contains:
    id:
      description: Job id.
      type: str
    status:
      description: One of C(queued), C(running), C(canceled), C(succeeded), C(failed).
      type: str
    task_type:
      description: Type of the task that produced the job.
      type: str
    schedule_at:
      description: When the job was scheduled to run.
      type: str
    created_at:
      description: When the job row was created.
      type: str
    started_at:
      description: When the job started, if it did.
      type: str
    stopped_at:
      description: When the job stopped, if it did.
      type: str
    log:
      description: Plain-text job log.
      type: str
      returned: when O(include_log=true)
total:
  description: Total number of jobs matching the filter, before pagination.
  returned: when listing
  type: int
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import (
    PlakarClient, PlakarError, argument_spec)


def slim(job):
    """Keep the stable scalars; job.task carries polymorphic config and
    resolved connector objects that are not a contract worth re-exporting."""
    task = job.get('task') or {}
    return {
        'id': job.get('id'),
        'status': job.get('status'),
        'task_type': task.get('type'),
        'schedule_at': job.get('schedule_at'),
        'created_at': job.get('created_at'),
        'started_at': job.get('started_at'),
        'stopped_at': job.get('stopped_at'),
    }


def main():
    spec = argument_spec()
    spec.update(
        job_id=dict(type='str', required=False),
        at_id=dict(type='str', required=False),
        task_type=dict(type='str', required=False,
                       choices=['backup', 'restore', 'sync', 'check', 'prune',
                                'rm', 'maintenance']),
        status=dict(type='str', required=False,
                    choices=['queued', 'running', 'canceled', 'succeeded', 'failed']),
        limit=dict(type='int', default=50),
        offset=dict(type='int', default=0),
        include_log=dict(type='bool', default=False),
    )
    module = AnsibleModule(
        argument_spec=spec,
        supports_check_mode=True,
        mutually_exclusive=[
            ('job_id', 'at_id'),
            ('job_id', 'task_type'), ('job_id', 'status'),
            ('at_id', 'task_type'), ('at_id', 'status'),
        ],
    )
    client = PlakarClient(module)

    try:
        result = {}
        if module.params.get('at_id'):
            job = client.at_status(module.params['at_id'])
            jobs = [job] if job else []
        elif module.params.get('job_id'):
            # No GET /scheduling/jobs/{id} in v1 (only /state and /log hang off
            # a job id), so one job means walking the paginated list.
            jobs = client_find_job(client, module.params['job_id'])
        else:
            res = client.request('GET', '/api/v1/scheduling/jobs',
                                 query={'limit': module.params['limit'],
                                        'offset': module.params['offset'],
                                        'task_type': module.params.get('task_type'),
                                        'task_status': module.params.get('status')})
            jobs = [slim(j) for j in (res.get('items') or [])]
            result['total'] = res.get('total')

        if module.params['include_log']:
            for job in jobs:
                try:
                    job['log'] = client.job_log(job['id'])
                except PlakarError:
                    job['log'] = ''

        result['jobs'] = jobs
        module.exit_json(changed=False, **result)
    except PlakarError as e:
        module.fail_json(msg=e.msg, status=e.status)


def client_find_job(client, job_id, page=200, max_pages=10):
    """Walk the paginated list looking for one job id."""
    for i in range(max_pages):
        res = client.request('GET', '/api/v1/scheduling/jobs',
                             query={'limit': page, 'offset': i * page})
        items = res.get('items') or []
        for j in items:
            if j.get('id') == job_id:
                return [slim(j)]
        if len(items) < page:
            break
    raise PlakarError('job %s not found' % job_id, status=404)


if __name__ == '__main__':
    main()
