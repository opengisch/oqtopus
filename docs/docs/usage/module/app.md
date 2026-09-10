# Application

A module separates its persistent data from its application logic. Tables live
in data schemas managed by the changelogs, while views, functions and triggers
live in dedicated application schemas that can be dropped and recreated at will.

In the **Module** tab, when the installed version matches the selected version,
the **Maintain** view exposes the two application actions.

## Drop app

Executes the module's drop handlers, removing the application schemas. The data
schemas are left untouched.

## (Re)create app

Executes the drop handlers followed by the create handlers, rebuilding the
application schemas from the current module version.

The dialog shows the parameters recorded at install time. Standard parameters
are read-only — changing them would desynchronise the application from the
data. Application parameters (those declared `app_only` by the module) can be
edited, so this is the way to switch an option such as a language or an
optional extension without reinstalling the module.

### Permissions

Dropping a schema discards every privilege granted on it, together with the
default privileges configured for it. The application schemas are therefore
granted the [configured permissions](role_management.md) again once they have
been recreated.

The roles found in the database are listed in the dialog under **Re-grant
permissions**, each with its own checkbox, so you can confirm which ones to
grant before the operation starts. The generic roles appear as **Generic
roles**, next to the DB-specific (suffixed) ones.

A role is checked when it currently holds a privilege on one of the module
schemas, since re-granting is there to restore what dropping them discards. In
the usual DB-specific setup the generic roles are deliberately created without
permissions, so they start unchecked — tick them to grant those too. If no role
holds any permission, because the application was already dropped, they are all
offered checked.

Uncheck the group, or every role in it, to leave the permissions alone — the
recreated schemas will then have no privilege until you grant them from
**Manage roles and users → Create and grant roles**.

!!! warning
    Before this was introduced, recreating the application silently left its
    schemas without any permission, and the roles had to be granted again by
    hand.
