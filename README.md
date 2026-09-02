# Ansible Collection — plakarkorp.plakar

Drive [Plakar](https://plakar.io) from Ansible playbooks: trigger backups and
restores, query job state, and declare repositories, connectors and SLA
policies through the Plakar management API. Built to run inside Red Hat
Ansible Automation Platform (or plain ansible-core >= 2.15).

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
| `plakarkorp.plakar.job_info` | Read job state, one job or a filtered list |
| `plakarkorp.plakar.repository` | Declare backup repositories (store connectors, kloset init included) |
| `plakarkorp.plakar.connector` | Declare source and destination connectors |
| `plakarkorp.plakar.sla_template` | Declare protection policies |
| `plakarkorp.plakar.sla_contract` | Bind a policy to a source |

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

    - name: Restore the latest snapshot onto the recovery target
      plakarkorp.plakar.restore:
        store: S3 Store
        destination: Recovery target

    - name: Any failed backups today?
      plakarkorp.plakar.job_info:
        task_type: backup
        status: failed
      register: failed
```

Backups and restores are asynchronous server-side: the modules poll until the
job stops (`wait: true`, the default, `wait_timeout: 600`), or return
immediately with `wait: false` for later polling with `job_info`.

Declaring the estate looks like this:

```yaml
- plakarkorp.plakar.repository:
    name: Offsite S3
    protocol: s3
    integration: s3
    resource: Ample Sky          # inventory resource, by URN or name
    compression: ZSTD
    fields:
      passphrase: "{{ vault_repo_passphrase }}"
      access_key: "{{ vault_s3_access_key }}"
      secret_access_key: "{{ vault_s3_secret_key }}"
      root: /backups

- plakarkorp.plakar.sla_template:
    name: Critical SLA
    environment: production
    temporalities:
      day: {frequency: 4, retention: 10, store: Offsite S3}

- plakarkorp.plakar.sla_contract:
    template: Critical SLA
    source: Production DB
```

## Multi-organization plays

An API key is bound to one organization. To operate in another organization
the account is a member of, set `organization_id` on the task — the badge is
re-scoped server-side, the key stays the same.

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

GPL-3.0-or-later (the Ansible ecosystem requirement for modules).
