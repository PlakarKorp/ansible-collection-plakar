# Ansible Collection — plakarkorp.plakar

Drive [Plakar](https://plakar.io) from Ansible playbooks: trigger backups and
restores, query job state, and declare stores and connectors through the
Plakar management API. Built to run inside Red Hat Ansible Automation
Platform (or plain ansible-core >= 2.15).

All modules talk HTTPS to the management API; nothing runs on the managed
hosts, so plays target `localhost` (or use `delegate_to`).

## Install

```sh
ansible-galaxy collection install plakarkorp.plakar
```

For AAP, add the collection to your execution environment — this repo ships a
ready [`execution-environment.yml`](execution-environment.yml):

```sh
ansible-builder build -t plakar-ee .
```

then point your AAP job templates at the resulting image, and put
`PLAKAR_API_URL` / `PLAKAR_API_KEY` in a credential type or the job's
environment.

## Setup

The collection authenticates with an API key belonging to a service account.
Once, as an administrator of your organization:

1. Create a service account and grant it the `operator` role ("runs what is
   already defined, and defines nothing").
2. Mint an API key for it (`pcp_ak_...`) — the key is shown once, and is bound
   to the organization it was minted in.

Then point the collection at your deployment, via module arguments or the
`PLAKAR_API_URL` / `PLAKAR_API_KEY` environment variables.

> A service account without a grant does not get errors — it gets empty
> lists. If a module reports "no connector named ...", check the grant first.

## Modules

| Module | Purpose |
| --- | --- |
| `plakarkorp.plakar.backup` | Trigger a backup of a source into a store |
| `plakarkorp.plakar.restore` | Restore a snapshot from a store onto a destination |
| `plakarkorp.plakar.sync` | Sync snapshots from one store into another |
| `plakarkorp.plakar.check` | Verify the integrity of a store's snapshots |
| `plakarkorp.plakar.prune` | Prune a store's snapshots by retention rule |
| `plakarkorp.plakar.job_info` | Read job state, one job or a filtered list |
| `plakarkorp.plakar.store` | Declare stores (initialized on creation) |
| `plakarkorp.plakar.connector` | Declare source and destination connectors |
| `plakarkorp.plakar.inventory` | Declare inventories (cloud providers or self-managed) |
| `plakarkorp.plakar.inventory_resource` | Declare resources in a self-managed inventory |
| `plakarkorp.plakar.inventory_sync` | Re-read what an inventory's provider holds |
| `plakarkorp.plakar.inventory_info` | Read inventories, coverage and resources |
| `plakarkorp.plakar.organization` | Declare organizations under your own |
| `plakarkorp.plakar.member` | Manage an organization's members (people and service accounts) |
| `plakarkorp.plakar.grant` | Grant and revoke roles to members |
| `plakarkorp.plakar.organization_info` | Read an organization, its members and grants |

Everything is addressed **by name**; the modules resolve names within the
organization at run time, and the declarative modules manage only the options
the playbook sets — anything else keeps its server-side value.

## Example

```yaml
- hosts: localhost
  gather_facts: false
  environment:
    PLAKAR_API_URL: https://plakar.example.com
    PLAKAR_API_KEY: "{{ vault_plakar_api_key }}"
  tasks:
    - name: Backup the production database
      plakarkorp.plakar.backup:
        source: Production DB
        store: S3 Store
        labels: [nightly]

    - name: Replicate the store offsite
      plakarkorp.plakar.sync:
        store: S3 Store
        to_store: Offsite S3

    - name: Restore the latest snapshot onto the recovery target
      plakarkorp.plakar.restore:
        store: S3 Store
        destination: Recovery target

    - name: Keep a daily snapshot for a week, a monthly one for a year
      plakarkorp.plakar.prune:
        store: S3 Store
        retention:
          day: 7
          per_day: 1
          month: 12
          per_month: 1
        group_by: dataset          # the rule holds per source, not store-wide
        tags: [nightly]            # only the nightly snapshots
        filters:
          ignore_tags: [do-not-prune]

    - name: Any failed backups today?
      plakarkorp.plakar.job_info:
        task_type: backup
        status: failed
      register: failed
```

Prune in check mode deletes nothing and reports what the rule would delete,
keep, and hold back (legal holds are never deleted).

Backups and restores are asynchronous server-side: the modules poll until the
job stops (`wait: true`, the default, `wait_timeout: 600`), or return
immediately with `wait: false` for later polling with `job_info`.

Declaring the estate looks like this:

```yaml
- plakarkorp.plakar.store:
    name: Offsite S3
    integration: s3
    resource: Ample Sky          # inventory resource, by URN or name
    fields:
      passphrase: "{{ vault_repo_passphrase }}"
      access_key: "{{ vault_s3_access_key }}"
      secret_access_key: "{{ vault_s3_secret_key }}"
      root: /backups
```

## Inventories

Connectors attach to **inventory resources** — the machines and services the
control plane knows about and tracks coverage for. A provider-backed
inventory watches a cloud account and fills itself on sync:

```yaml
- plakarkorp.plakar.inventory:
    name: Production Scaleway
    type: scaleway
    configuration:
      scw_project_id: "{{ scw_project_id }}"
      scw_access_key: "{{ vault_scw_access_key }}"
      scw_secret_key: "{{ vault_scw_secret_key }}"

- plakarkorp.plakar.inventory_sync:
    name: Production Scaleway
```

A **self-managed** inventory holds whatever the playbook declares — which is
how a fleet Ansible already knows becomes a coverage inventory the control
plane tracks. Resources are keyed by URN, so the mirroring is idempotent and
can run on every inventory change:

```yaml
- name: Mirror the Ansible inventory into the control plane
  hosts: localhost
  gather_facts: false
  tasks:
    - plakarkorp.plakar.inventory:
        name: Ansible fleet
        type: self-managed

    - plakarkorp.plakar.inventory_resource:
        inventory: Ansible fleet
        urn: "urn:ansible:{{ item }}"
        name: "{{ item }}"
        class: "{{ hostvars[item].plakar_class | default('compute') }}"
        endpoints: ["{{ hostvars[item].ansible_host | default(item) }}"]
        tags: "{{ hostvars[item].plakar_tags | default([]) + ['ansible-managed'] }}"
      loop: "{{ groups['all'] }}"

    - plakarkorp.plakar.inventory_info:
        name: Ansible fleet
        include_resources: true
      register: fleet
```

`inventory_info` reports each inventory's coverage (protected, unprotected,
excluded) — freshly mirrored hosts show up unprotected until a connector and
a schedule take care of them. Retiring a resource is `state: absent` on its
URN. Stick to the classes the control plane knows (`compute`, `database`,
`file-storage`, `object-storage`, `block-storage`, `network`, `hypervisor`,
`service`, ...): the API stores unknown ones as-is but the UI and coverage
grouping key off the known set.

## Organizations, members and grants

Under an owner's key you can carve out sub-organizations and set up who is in
them and what they may do. A membership carries no permission — being in an
organization and being allowed to do something are separate facts, so they are
separate modules: `member` puts a person or a service account in, `grant`
gives that member a role.

```yaml
- name: Stand up a tenant with its people and permissions
  hosts: localhost
  gather_facts: false
  tasks:
    - plakarkorp.plakar.organization:
        name: Lyon

    - plakarkorp.plakar.member:
        organization: Lyon
        email: alice@example.com
        name: Alice
      register: alice

    # A brand-new account comes back with a one-time password; an address
    # that already had one just gains the membership. Relay it once.
    - ansible.builtin.debug:
        msg: "Alice's initial password: {{ alice.generated_password }}"
      when: alice.account_created | default(false)

    - plakarkorp.plakar.grant:
        organization: Lyon
        subject: alice@example.com
        role: auditor

    # A service account for automation — no address, its API key is minted
    # in the Plakar UI (an application user cannot mint its own).
    - plakarkorp.plakar.member:
        organization: Lyon
        name: nightly-automation
        service: true

    - plakarkorp.plakar.grant:
        organization: Lyon
        subject: nightly-automation      # a service account by name
        role: operator
```

Role names come from the server's catalogue — the standard tier is `owner`,
`administrator`, `operator` and `auditor`; an unknown name fails with the
list. `organization_info` reads a tenant back with `include_members` and
`include_grants`. Removing a member removes the membership, not the person's
account; an organization deletes only once it holds no other members.

## Multi-organization plays

An API key is bound to one organization. To operate in another organization
the account is a member of, set `organization_id` on the task — the badge is
re-scoped server-side, the key stays the same. The organization modules also
take an `organization:` name to act on a tenant in the key's own subtree
without re-scoping.

## Development

Integration tests run against a live dev stack:

```sh
PLAKAR_API_URL=http://localhost:8080 PLAKAR_API_KEY=pcp_ak_... \
  ansible-playbook tests/integration/e2e.yml
```

Sanity:

```sh
ansible-test sanity --docker default
```

## License

ISC, like Plakar itself. ansible-core's sanity suite conventionally expects a
GPLv3 header on module files; the collection deviates deliberately (ISC is
GPL-compatible) and carries the sanity-ignore entries for it.
