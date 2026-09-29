# Mobile App Screen Permissions

Karmavitta uses existing ERPNext System Users. The screen matrix controls mobile
visibility only; it does not create users, alter ERPNext roles, or grant access to
records and actions.

## Update the site

From the bench directory, build the Karmavitta assets and migrate the site:

```bash
bench build --app karmavitta
bench --site YOUR-SITE migrate
```

The migration installs the **Mobile App Permissions** Desk page and the
**Mobile App Permission Screen** child table. The page is linked from the **Mobile
App Management** workspace and is available to System Managers.

## Configure a user

1. Open **Mobile App Management → Mobile App Permissions**.
2. Select **Add Mobile App Permission**. Searchable User selection is limited to
   enabled ERPNext System Users.
3. Review the selected user's name, email, enabled status, and assigned roles.
   Roles are shown as context only; this page does not change them.
4. Use the grouped screen switches, module toggles, search, Select All/Deselect
   All, and per-module Enable all/Disable all controls.
5. Select **Save**. The screen rows are stored on the user's
   **Mobile App Permission** record. Selecting an already-configured user opens
   that user's existing record instead of creating a duplicate.

New installations default users without a screen profile to no mobile screens.
The existing **Allow ERP-permitted screens by default** setting remains available
for sites that intentionally configured that behavior before this update. A
user's saved screen profile overrides that fallback for mobile visibility.

## Mobile app behavior

The page and app API share the registry in
`karmavitta/mobile_app_management/catalog.py`. Its keys reuse the app's current
module, route, and DocType identifiers, and include enabled ERPNext reports that
already appear in the app's Reports screen. The app requests
`karmavitta.api.mobile_permissions.get_mobile_screen_permissions` after login and
uses the effective permission object returned by the API. Existing route guards
also block direct navigation to disabled screens.

Every enabled screen remains subject to the user's ERPNext permissions. A mobile
screen checkbox cannot grant DocType access or bypass API permission checks. The
existing Face Attendance camera, enrollment, ArcFace, check-in/check-out, and API
implementation is unchanged; the matrix controls visibility only.

Older `Mobile App Permission Rule` rows remain in the database for compatibility
with existing sites. The new page does not expose role-based or action-level rule
editing.
