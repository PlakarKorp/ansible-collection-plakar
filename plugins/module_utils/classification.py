# -*- coding: utf-8 -*-
# Copyright (c) 2026 PlakarKorp
# ISC License (see LICENSE)

# Shared implementation of the environment and data_class modules. An
# organization keeps two labelling lists, which behave alike in v1: a list of
# plain strings, a create that is an upsert (an existing name answers 200, no
# conflict) and a delete by name. A name is its own identity: there is nothing
# to update.

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.module_utils.six.moves.urllib.parse import quote

# Per kind: the route segment, the create body key and the listing key.
KINDS = {
    'environment': ('environments', 'environment', 'environments'),
    'data_class': ('data_classes', 'class', 'classes'),
}


def classification_options():
    """Options shared by the environment and data_class modules."""
    return dict(
        name=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )


def run_classification_module(module, client, kind):
    segment, field, listing = KINDS[kind]
    name = module.params['name']
    if not name:
        # The API takes an empty name and offers no route to delete it.
        module.fail_json(msg='name must not be empty')

    base = '/api/v1/account/organizations/%s/%s' % (client.org_id(), segment)
    # The listing is compared exactly; the search route matches loosely.
    exists = name in ((client.request('GET', base) or {}).get(listing) or [])
    result = {kind: {'name': name}}

    if module.params['state'] == 'absent':
        if not exists:
            module.exit_json(changed=False)
        if not module.check_mode:
            # The whole name is escaped: a slash in it would address another
            # route, a percent sign another name.
            client.request('DELETE', '%s/%s' % (base, quote(name, safe='')), ok=(200, 204))
        module.exit_json(changed=True, **result)

    if not exists and not module.check_mode:
        client.request('POST', base, body={field: name}, ok=(200, 201))
    module.exit_json(changed=not exists, **result)
