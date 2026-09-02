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
