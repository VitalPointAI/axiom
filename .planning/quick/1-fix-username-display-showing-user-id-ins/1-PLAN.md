---
phase: quick
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - web/components/auth-provider.tsx
  - web/app/dashboard/layout.tsx
  - web/app/dashboard/page.tsx
  - web/components/login-buttons.tsx
autonomous: true
requirements: [FIX-USERNAME-DISPLAY]

must_haves:
  truths:
    - "Dashboard header shows user's name/email/codename, never their numeric user ID"
    - "Dashboard page shows 'Welcome back, <name>' with actual name, not numeric ID"
    - "Login buttons area shows user's name, not numeric ID"
  artifacts:
    - path: "web/components/auth-provider.tsx"
      provides: "Improved nearAccountId fallback chain including username"
      contains: "u.username"
    - path: "web/app/dashboard/layout.tsx"
      provides: "Header welcome using display_name"
      contains: "display_name"
    - path: "web/app/dashboard/page.tsx"
      provides: "Page welcome using display_name"
      contains: "display_name"
  key_links:
    - from: "web/components/auth-provider.tsx"
      to: "/auth/session API"
      via: "apiClient.get, maps session fields to User object"
      pattern: "u\\.username"
---

<objective>
Fix username display across the dashboard. Currently shows "Welcome, 3" and "Welcome back, 3" where "3" is the user's numeric database ID. Should show the user's actual name (username, email, codename, or near_account_id).

Purpose: Users see a confusing numeric ID instead of their name throughout the app.
Output: All welcome/display-name locations show meaningful user identifiers.
</objective>

<execution_context>
@/home/vitalpointai/.claude/get-shit-done/workflows/execute-plan.md
@/home/vitalpointai/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@web/components/auth-provider.tsx
@web/app/dashboard/layout.tsx
@web/app/dashboard/page.tsx
@web/components/login-buttons.tsx
@api/auth/_user_helpers.py

<interfaces>
<!-- The /auth/session endpoint returns this shape (from api/auth/router.py): -->
```typescript
// SessionResponse.user fields available from backend:
{
  user_id: number;         // Always present (PK)
  near_account_id?: string; // NEAR wallet address (nullable)
  username?: string;        // Username from registration (nullable)
  email?: string;           // Email address (nullable)
  codename?: string;        // Display codename (nullable)
  is_admin?: boolean;       // Admin flag
}
```

<!-- Current User interface in auth-provider.tsx: -->
```typescript
interface User {
  id: string;
  email?: string;
  near_account_id?: string;
  display_name?: string;
  is_admin?: boolean;
  nearAccountId: string;    // PROBLEMATIC: fallback chain ends with String(user_id)
  codename?: string;
  createdAt?: string;
}
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix auth-provider fallback chain and add displayName helper</name>
  <files>web/components/auth-provider.tsx</files>
  <action>
In `auth-provider.tsx`, fix the `checkSession` callback (line 50-59) where the User object is constructed from the session response:

1. Fix the `nearAccountId` fallback chain on line 56. Currently:
   ```
   nearAccountId: u.near_account_id || u.email || u.codename || String(u.user_id)
   ```
   Change to include `u.username` before the numeric ID fallback:
   ```
   nearAccountId: u.near_account_id || u.username || u.email || u.codename || String(u.user_id)
   ```

2. Fix the `display_name` mapping on line 54. Currently:
   ```
   display_name: u.codename || u.username
   ```
   Change to a richer fallback chain that never falls through to numeric ID:
   ```
   display_name: u.codename || u.username || u.email || u.near_account_id || 'User'
   ```
   This ensures `display_name` is always a human-readable string. The literal 'User' is the last resort (better than showing "3").

No changes to the User interface needed — `display_name` is already defined as `string | undefined` which is sufficient since we now guarantee it is always set.
  </action>
  <verify>
    <automated>cd /home/vitalpointai/projects/Axiom && npx tsc --noEmit --project web/tsconfig.json 2>&1 | head -20</automated>
  </verify>
  <done>auth-provider.tsx constructs display_name with full fallback chain (codename > username > email > near_account_id > 'User') and nearAccountId includes username in its chain</done>
</task>

<task type="auto">
  <name>Task 2: Update dashboard and login-buttons to use display_name instead of nearAccountId</name>
  <files>web/app/dashboard/layout.tsx, web/app/dashboard/page.tsx, web/components/login-buttons.tsx</files>
  <action>
Three files currently display `user.nearAccountId` where they should display `user.display_name` (which is now guaranteed to be a meaningful string from Task 1):

1. **web/app/dashboard/layout.tsx line 118** — Header welcome message.
   Change:
   ```
   Welcome, <span className="text-white font-medium">{user.nearAccountId}</span>
   ```
   To:
   ```
   Welcome, <span className="text-white font-medium">{user.display_name}</span>
   ```

2. **web/app/dashboard/page.tsx line 40** — Dashboard page welcome.
   Change:
   ```
   Welcome back, {user?.nearAccountId}
   ```
   To:
   ```
   Welcome back, {user?.display_name}
   ```

3. **web/components/login-buttons.tsx lines 22-24** — User display in header buttons.
   Currently shows `user.codename` with fallback to truncated `user.nearAccountId`. Change:
   ```
   {user.codename || (user.nearAccountId.length > 20
     ? `${user.nearAccountId.slice(0, 8)}...${user.nearAccountId.slice(-8)}`
     : user.nearAccountId)}
   ```
   To:
   ```
   {user.display_name || (user.nearAccountId.length > 20
     ? `${user.nearAccountId.slice(0, 8)}...${user.nearAccountId.slice(-8)}`
     : user.nearAccountId)}
   ```
   This uses `display_name` first (which already includes codename in its chain), with the truncated nearAccountId as fallback for NEAR-wallet-only users where a long address is all that is available.
  </action>
  <verify>
    <automated>cd /home/vitalpointai/projects/Axiom && npx tsc --noEmit --project web/tsconfig.json 2>&1 | head -20 && grep -n "nearAccountId" web/app/dashboard/layout.tsx web/app/dashboard/page.tsx | grep -i "welcome" ; echo "Should show no matches for nearAccountId in welcome lines"</automated>
  </verify>
  <done>All three welcome/display locations use user.display_name. No location shows numeric user ID. NEAR wallet addresses still display correctly for wallet-specific contexts.</done>
</task>

</tasks>

<verification>
- TypeScript compilation passes with no errors
- No remaining instances of `user.nearAccountId` or `user?.nearAccountId` in welcome/greeting contexts
- `display_name` fallback chain in auth-provider guarantees a non-numeric-ID string
</verification>

<success_criteria>
- Dashboard header shows "Welcome, [name]" where [name] is the user's codename, username, email, or NEAR account — never a bare numeric ID like "3"
- Dashboard page shows "Welcome back, [name]" with the same logic
- Login buttons show the user's display name
- TypeScript compiles without errors
</success_criteria>

<output>
After completion, create `.planning/quick/1-fix-username-display-showing-user-id-ins/1-SUMMARY.md`
</output>
