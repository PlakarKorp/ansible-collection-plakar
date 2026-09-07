# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

# The one place that knows the wire. Modules speak in names and intents;
# everything v1-shaped (verb irregularities, the at_id poll loop, badge
# expiry, org re-scoping) is confined here so a later v2 swap touches only
# this file.

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import json
import time

from ansible.module_utils.basic import env_fallback
from ansible.module_utils.six.moves.urllib.parse import quote
from ansible.module_utils.urls import fetch_url


def argument_spec():
    """Connection options shared by every module in the collection."""
    return dict(
        api_url=dict(
            type='str',
            required=False,
            fallback=(env_fallback, ['PLAKAR_API_URL']),
        ),
        api_key=dict(
            type='str',
            required=False,
            no_log=True,
            fallback=(env_fallback, ['PLAKAR_API_KEY']),
        ),
        organization_id=dict(type='str', required=False),
        validate_certs=dict(type='bool', default=True),
        timeout=dict(type='int', default=30),
    )


class PlakarError(Exception):
    def __init__(self, msg, status=None, body=None):
        super(PlakarError, self).__init__(msg)
        self.msg = msg
        self.status = status
        self.body = body


class PlakarClient(object):
    """Badge-carrying HTTP client for the Plakar management API (v1).

    Login is lazy and re-done transparently when the badge expires (the API
    answers 401; badges are bounded by the organization's badge_ttl_seconds).
    A key is bound to one organization; asking for another organization_id
    exchanges the badge via POST /auth/badge. Badges are cached per org so a
    play alternating between organizations does not re-login on every task.
    """

    def __init__(self, module):
        self.module = module
        self.api_url = (module.params.get('api_url') or '').rstrip('/')
        self.api_key = module.params.get('api_key')
        self.organization_id = module.params.get('organization_id')
        self.timeout = module.params.get('timeout')
        if not self.api_url:
            module.fail_json(msg='api_url is required (or set PLAKAR_API_URL)')
        if not self.api_key:
            module.fail_json(msg='api_key is required (or set PLAKAR_API_KEY)')
        self._badges = {}  # org key ('' = the key's own org) -> token

    # --- auth -------------------------------------------------------------

    def _login(self):
        status, body = self._raw('POST', '/api/v1/auth/login/apikey',
                                 body={'api_key': self.api_key}, token=None)
        if status != 200:
            raise PlakarError('API key login failed', status=status, body=body)
        return body['token']

    def _token(self, refresh=False):
        org = self.organization_id or ''
        if refresh or org not in self._badges:
            token = self._badges.get('') if not refresh else None
            if token is None:
                token = self._login()
                self._badges[''] = token
            if org:
                status, body = self._raw('POST', '/api/v1/auth/badge',
                                         body={'organization_id': org}, token=token)
                if status != 200:
                    raise PlakarError('badge exchange for organization %s failed' % org,
                                      status=status, body=body)
                self._badges[org] = body['token']
        return self._badges[org]

    # --- transport ----------------------------------------------------------

    def _raw(self, method, path, body=None, query=None, token=None):
        url = self.api_url + path
        if query:
            pairs = ['%s=%s' % (k, v) for k, v in query.items() if v is not None]
            if pairs:
                url += '?' + '&'.join(pairs)
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer %s' % token
        data = json.dumps(body) if body is not None else None
        resp, info = fetch_url(self.module, url, method=method, data=data,
                               headers=headers, timeout=self.timeout)
        status = info['status']
        if status == -1:
            raise PlakarError('cannot reach %s: %s' % (url, info.get('msg')), status=-1)
        raw = resp.read() if resp else (info.get('body') or b'')
        if isinstance(raw, str):
            raw = raw.encode('utf-8')
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = raw.decode('utf-8', errors='replace')
        return status, parsed

    def request(self, method, path, body=None, query=None, ok=(200,)):
        """Authenticated request; one transparent re-login on 401."""
        status, parsed = self._raw(method, path, body=body, query=query,
                                   token=self._token())
        if status == 401:
            status, parsed = self._raw(method, path, body=body, query=query,
                                       token=self._token(refresh=True))
        if status not in ok:
            detail = parsed.get('detail') if isinstance(parsed, dict) else parsed
            raise PlakarError('%s %s answered %s: %s' % (method, path, status, detail),
                              status=status, body=parsed)
        return parsed

    def request_text(self, path):
        """GET returning text/plain (job logs)."""
        status, parsed = self._raw('GET', path, token=self._token())
        if status == 401:
            status, parsed = self._raw('GET', path, token=self._token(refresh=True))
        if status != 200:
            raise PlakarError('GET %s answered %s' % (path, status), status=status)
        return parsed if isinstance(parsed, str) else json.dumps(parsed)

    # --- resources ----------------------------------------------------------

    def me(self):
        return self.request('GET', '/api/v1/account/me')

    def org_id(self):
        # The badge knows its organization but v1 only hands it back through
        # /account/me. organization_id param short-circuits the extra call.
        if self.organization_id:
            return self.organization_id
        return self.me()['organization_id']

    def list_connectors(self, kind):
        """kind: source|store|destination."""
        res = self.request('GET',
                           '/api/v1/account/organizations/%s/connectors' % self.org_id(),
                           query={'type': kind})
        return res.get('items') or []

    def find_connector(self, kind, name):
        """One connector by name, None when absent, error on a duplicate name."""
        matches = [c for c in self.list_connectors(kind) if c.get('name') == name]
        if len(matches) > 1:
            raise PlakarError('%d %s connectors named %r — names must be unique to '
                              'address them from a playbook' % (len(matches), kind, name))
        return matches[0] if matches else None

    def connector_by_name(self, kind, name):
        """Like find_connector, but absence is an error naming the visible ones."""
        found = self.find_connector(kind, name)
        if found is None:
            items = self.list_connectors(kind)
            known = ', '.join(sorted(repr(c.get('name')) for c in items)) or '(none visible)'
            raise PlakarError(
                'no %s connector named %r — visible: %s. An empty list can also mean '
                'the API key\'s user holds no grant in the organization.'
                % (kind, name, known))
        return found

    def installed_integration(self, name):
        res = self.request('GET', '/api/v1/integrations/installed')
        items = res if isinstance(res, list) else (res.get('items') or [])
        matches = [i for i in items if i.get('name') == name]
        if not matches:
            known = ', '.join(sorted(repr(i.get('name')) for i in items)) or '(none installed)'
            raise PlakarError('no installed integration named %r — installed: %s'
                              % (name, known))
        return matches[0]

    def resource_ref(self, value):
        """A resource across all inventories, by URN first, then by name.

        The route serves at most 50 rows per page whatever limit is asked;
        the search filter narrows server-side, exact matching happens here.
        """
        items, offset = [], 0
        while True:
            res = self.request('GET', '/api/v1/inventories/resources',
                               query={'limit': 50, 'offset': offset,
                                      'search': quote(value)})
            page = res.get('items') or []
            items.extend(page)
            offset += len(page)
            if not page or offset >= (res.get('total') or 0):
                break
        by_urn = [r for r in items if r.get('urn') == value]
        if by_urn:
            return by_urn[0]
        by_name = [r for r in items if r.get('name') == value]
        if len(by_name) > 1:
            raise PlakarError('%d resources named %r — use the URN to disambiguate'
                              % (len(by_name), value))
        if by_name:
            return by_name[0]
        raise PlakarError('no resource with URN or name %r' % value)

    def list_inventories(self):
        """All inventories of the organization (the route pages at 50)."""
        items, offset = [], 0
        while True:
            res = self.request('GET',
                               '/api/v1/account/organizations/%s/inventories' % self.org_id(),
                               query={'limit': 50, 'offset': offset})
            page = res.get('items') or []
            items.extend(page)
            offset += len(page)
            if not page or offset >= (res.get('total') or 0):
                break
        return items

    def find_inventory(self, name):
        """One inventory by name, None when absent, error on a duplicate name."""
        matches = [i for i in self.list_inventories() if i.get('name') == name]
        if len(matches) > 1:
            raise PlakarError('%d inventories named %r — names must be unique to '
                              'address them from a playbook' % (len(matches), name))
        return matches[0] if matches else None

    def inventory_by_name(self, name):
        """Like find_inventory, but absence is an error naming the visible ones."""
        found = self.find_inventory(name)
        if found is None:
            items = self.list_inventories()
            known = ', '.join(sorted(repr(i.get('name')) for i in items)) or '(none visible)'
            raise PlakarError(
                'no inventory named %r — visible: %s. An empty list can also mean '
                'the API key\'s user holds no grant in the organization.'
                % (name, known))
        return found

    def inventory_resources(self, inventory_id, search=None):
        """Resources of one inventory (the route pages at 50)."""
        items, offset = [], 0
        while True:
            query = {'limit': 50, 'offset': offset}
            if search:
                query['search'] = quote(search)
            res = self.request('GET', '/api/v1/inventories/%s/resources' % inventory_id,
                               query=query)
            page = res.get('items') or []
            items.extend(page)
            offset += len(page)
            if not page or offset >= (res.get('total') or 0):
                break
        return items

    def find_inventory_resource(self, inventory_id, urn):
        """One resource by URN within an inventory, None when absent."""
        matches = [r for r in self.inventory_resources(inventory_id, search=urn)
                   if r.get('urn') == urn]
        return matches[0] if matches else None

    def snapshots(self, store_id):
        res = self.request('GET', '/api/v1/snapshots/store/%s' % store_id)
        return res.get('items') or []

    def latest_snapshot(self, store_id):
        snaps = self.snapshots(store_id)
        if not snaps:
            raise PlakarError('store %s holds no snapshots' % store_id)
        return sorted(snaps, key=lambda s: s.get('creation_time') or '')[-1]

    # --- one-shot runs --------------------------------------------------------

    def run_task(self, task_type, origin_id, target_id=None, config=None, edge_tags=None):
        body = {'type': task_type, 'origin_id': origin_id}
        if target_id:
            body['target_id'] = target_id
        if config:
            body['config'] = config
        if edge_tags:
            body['edge_tags'] = edge_tags
        res = self.request('POST', '/api/v1/scheduling/scheduler/run', body=body)
        return res['id']  # the schedulers_at id, not a job id

    def at_status(self, at_id):
        """Minimal view of a one-shot run: (job_id, status, started, stopped).

        While the scheduler has not materialized a job the response omits the
        job key entirely (it is not job:null) — both read as 'pending' here.
        Only stable scalars are extracted: job.task.config is polymorphic and
        the full shape is not a contract worth depending on.
        """
        res = self.request('GET', '/api/v1/scheduling/scheduler/run/%s' % at_id)
        job = res.get('job') or None
        if not job:
            return None
        return {
            'id': job.get('id'),
            'status': job.get('status'),
            'task_type': (job.get('task') or {}).get('type'),
            'started_at': job.get('started_at'),
            'stopped_at': job.get('stopped_at'),
        }

    def wait_at(self, at_id, timeout=600, interval=2):
        deadline = time.time() + timeout
        while True:
            job = self.at_status(at_id)
            if job and job['stopped_at'] is not None:
                return job
            if time.time() > deadline:
                raise PlakarError('timed out after %ss waiting for run %s (last: %s)'
                                  % (timeout, at_id, (job or {}).get('status', 'pending')))
            time.sleep(interval)

    def job_log(self, job_id):
        return self.request_text('/api/v1/scheduling/jobs/%s/log' % job_id)


def run_wait_options():
    """Arguments shared by the action modules (backup, restore)."""
    return dict(
        wait=dict(type='bool', default=True),
        wait_timeout=dict(type='int', default=600),
        edge_tags=dict(type='list', elements='str', required=False),
    )
