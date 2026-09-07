===============================
Plakarkorp.Plakar Release Notes
===============================

.. contents:: Topics

v0.1.0
======

Release Summary
---------------

First release of the collection: trigger backups, restores, store syncs,
integrity checks and retention prunes, query job state, and declare stores,
connectors and inventories against the Plakar management API.

New Modules
-----------

- plakarkorp.plakar.backup - Trigger a Plakar backup.
- plakarkorp.plakar.check - Verify the integrity of Plakar snapshots.
- plakarkorp.plakar.connector - Manage Plakar source and destination connectors.
- plakarkorp.plakar.inventory - Manage Plakar inventories.
- plakarkorp.plakar.inventory_info - Read Plakar inventories and their resources.
- plakarkorp.plakar.inventory_resource - Manage resources in a self-managed Plakar inventory.
- plakarkorp.plakar.inventory_sync - Synchronize a Plakar inventory against its provider.
- plakarkorp.plakar.job_info - Query Plakar job state.
- plakarkorp.plakar.prune - Prune snapshots from a Plakar store by retention rule.
- plakarkorp.plakar.restore - Trigger a Plakar restore.
- plakarkorp.plakar.store - Manage Plakar stores.
- plakarkorp.plakar.sync - Sync snapshots between Plakar stores.
