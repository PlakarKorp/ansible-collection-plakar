# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

# Shared implementation of the organization, member and grant modules.
# Memberships carry no rank — what a member may do is a grant, a
# (subject, role) pair on the organization — so the three modules stay
# separate and each manages exactly one of those facts. Membership creation
# goes through the invitation route with auto_accept (the admin path): it
# covers a new person (a one-time generated password comes back), an
# existing account (membership only, no password), and a service account
# (is_service, address minted server-side).

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.plakarkorp.plakar.plugins.module_utils.client import PlakarError


def target_organization(module, client):
    """The organization a task acts on: `organization` by name, else the badge's."""
    name = module.params.get('organization')
    if name:
        return client.organization_by_name(name)
    org_id = client.org_id()
    return client.request('GET', '/api/v1/account/organizations/%s' % org_id)


def _org_slim(org):
    return {
        'id': org.get('id'),
        'name': org.get('name'),
        'type': org.get('type'),
        'parent_id': org.get('parent_id'),
    }


def run_organization_module(module, client):
    params = module.params
    name = params['name']

    current = client.resolve_organization(name)

    if params['state'] == 'absent':
        if current is None:
            module.exit_json(changed=False)
        if not module.check_mode:
            client.request('DELETE', '/api/v1/account/organizations/%s' % current['id'],
                           ok=(200, 204))
        module.exit_json(changed=True, organization=_org_slim(current))

    if current is not None:
        # v1 has no organization update route: name is the key, and info/type
        # are create-only. Existing means done.
        module.exit_json(changed=False, organization=_org_slim(current))

    parent_id = client.org_id()
    if params.get('parent'):
        parent_id = client.organization_by_name(params['parent'])['id']

    if module.check_mode:
        module.exit_json(changed=True, organization={'name': name})

    body = {
        'name': name,
        'type': params.get('type') or 'enterprise',
        'info': params.get('info') or {},
        'parent_id': parent_id,
    }
    created = client.request('POST', '/api/v1/account/organizations',
                             body=body, ok=(200, 201))
    module.exit_json(changed=True, organization=_org_slim(created))


def _member_slim(member):
    return {
        'user_id': member.get('user_id'),
        'email': member.get('email'),
        'account': member.get('account'),
        'name': member.get('name'),
        'is_service': member.get('is_service'),
    }


def run_member_module(module, client):
    params = module.params
    email = params.get('email')
    name = params.get('name')
    service = bool(params.get('service'))

    if service and email:
        module.fail_json(msg='a service account has no email; its address is '
                             'minted server-side — name it instead')
    if not service and not email:
        module.fail_json(msg='email is required for a person (or set service: '
                             'true and a name for an application user)')
    if service and not name:
        module.fail_json(msg='name is required for a service account')

    org = target_organization(module, client)
    current = client.find_member(org['id'], email=email, name=None if email else name)

    if params['state'] == 'absent':
        if current is None:
            module.exit_json(changed=False)
        if not module.check_mode:
            client.request('DELETE', '/api/v1/account/organizations/%s/members/%s'
                           % (org['id'], current['user_id']), ok=(200, 204))
        module.exit_json(changed=True, member=_member_slim(current))

    if current is not None:
        module.exit_json(changed=False, member=_member_slim(current))

    if module.check_mode:
        module.exit_json(changed=True, member={'email': email, 'name': name,
                                               'is_service': service})

    body = {'auto_accept': True, 'is_service': service}
    if name:
        body['name'] = name
    if email:
        body['email'] = email
    res = client.request('POST', '/api/v1/account/organizations/%s/invitations'
                         % org['id'], body=body, ok=(200, 201))
    accepted = res.get('accepted') or {}
    member = {
        'user_id': accepted.get('user_id'),
        'email': accepted.get('email'),
        'account': accepted.get('account'),
        'name': name,
        'is_service': service,
    }
    # The generated password exists only when the server minted a credential
    # for a brand-new person; it is shown exactly once, here.
    module.exit_json(changed=True, member=member,
                     account_created=bool(accepted.get('account_created')),
                     generated_password=accepted.get('generated_password'))


def _grant_slim(grant):
    subject = grant.get('subject') or {}
    role = grant.get('role') or {}
    return {
        'id': grant.get('id'),
        'subject': {'type': subject.get('type'), 'id': subject.get('id'),
                    'name': subject.get('name'), 'email': subject.get('email')},
        'role': role.get('name'),
    }


def run_grant_module(module, client):
    params = module.params
    role = params['role']
    subject = params['subject']

    org = target_organization(module, client)

    # The subject is a member of that organization, by email or by name
    # (service accounts have no address a play would know).
    member = client.find_member(org['id'], email=subject if '@' in subject else None,
                                name=None if '@' in subject else subject)
    if member is None:
        if params['state'] == 'absent':
            module.exit_json(changed=False)
        raise PlakarError('no member %r in organization %r — the subject must '
                          'be a member before it can hold a grant'
                          % (subject, org.get('name')))

    grants = client.list_grants(org['id'])
    matches = [g for g in grants
               if (g.get('subject') or {}).get('id') == member['user_id']
               and (g.get('role') or {}).get('name') == role]

    if params['state'] == 'absent':
        if not matches:
            module.exit_json(changed=False)
        if not module.check_mode:
            client.request('DELETE', '/api/v1/account/organizations/%s/access/%s'
                           % (org['id'], matches[0]['id']), ok=(200, 204))
        module.exit_json(changed=True, grant=_grant_slim(matches[0]))

    if matches:
        module.exit_json(changed=False, grant=_grant_slim(matches[0]))

    known = client.role_names()
    if known and role not in known:
        module.fail_json(msg='unknown role %r — the catalogue holds: %s'
                             % (role, ', '.join(known)))

    if module.check_mode:
        module.exit_json(changed=True, grant={'subject': subject, 'role': role})

    created = client.request('POST', '/api/v1/account/organizations/%s/access'
                             % org['id'],
                             body={'subject_type': 'user',
                                   'subject_id': member['user_id'],
                                   'role_name': role}, ok=(200, 201))
    module.exit_json(changed=True, grant=_grant_slim(created))
