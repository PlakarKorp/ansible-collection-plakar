# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


class ModuleDocFragment(object):
    DOCUMENTATION = r'''
options:
  api_url:
    description:
      - Base URL of the Plakar management API, for example C(https://plakar.example.com).
      - Falls back to the E(PLAKAR_API_URL) environment variable.
    type: str
  api_key:
    description:
      - API key of a service account, as minted by the Plakar API
        (C(pcp_ak_...)). API keys authenticate without a second factor and
        are bound to one organization.
      - The service account must hold a role in the organization (the
        C(operator) role suffices for running backups and restores); without
        a grant the API answers with empty lists rather than errors.
      - Falls back to the E(PLAKAR_API_KEY) environment variable.
    type: str
  organization_id:
    description:
      - UUID of the organization to operate in, when different from the one
        the API key is bound to. The badge is re-scoped once per organization
        and cached for the duration of the task.
    type: str
  validate_certs:
    description:
      - Whether to validate TLS certificates when talking to the API.
    type: bool
    default: true
  timeout:
    description:
      - Timeout in seconds for each individual API request (not for job
        completion; the action modules have C(wait_timeout) for that).
    type: int
    default: 30
requirements: []
notes:
  - All modules talk only to the Plakar management API over HTTPS; nothing
    runs on the managed hosts, so plays typically target C(localhost) or use
    C(delegate_to).
'''

    ACTION = r'''
options:
  wait:
    description:
      - Whether to wait for the triggered job to finish.
      - When false, the module returns as soon as the run is accepted; poll it
        later with M(plakarkorp.plakar.job_info).
    type: bool
    default: true
  wait_timeout:
    description:
      - Seconds to wait for the job to finish before failing.
    type: int
    default: 600
  edge_tags:
    description:
      - Select a remote edge by tags (all must match) to execute the job,
        falling back to local execution when no edge matches.
    type: list
    elements: str
'''

    SECRETS = r'''
options:
  update_secrets:
    description:
      - When to send a value the API does not show. Since v0.19 the Plakar
        Control Plane leaves the value of a sensitive field out of what it
        returns, so the module cannot tell whether the one in the playbook
        differs from the one stored.
      - V(on_create) sends such a value at creation only. Later runs leave
        the stored one alone and report no change for it, also when another
        option of the same task is updated.
      - V(always) sends it on every run, which then reports a change each
        time. Use it for the run that rotates a credential.
      - A value that references a secret provider is always shown, and so
        always compared, as is every value on an older Control Plane.
    type: str
    default: on_create
    choices: [on_create, always]
    version_added: 0.9.4
'''
