# Issue tracker: GitHub

Issues and specs live in GitHub Issues. Use the `gh` CLI.
Infer the repository from `git remote -v`. Without a remote, ask for `owner/repo` and pass `--repo owner/repo` to issue commands.

## Operations
- Publish: `gh issue create --title "..." --body "..."`. Use a heredoc for multiline bodies.
- Fetch: `gh issue view <number> --comments`; also fetch labels.
- List: `gh issue list --state open --json number,title,body,labels,comments`. Filter with `--label` and `--state` as needed.
- Comment: `gh issue comment <number> --body "..."`
- Labels: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`
- Close: `gh issue close <number> --comment "..."`

## Pull requests as a triage surface
**PRs as a request surface: no.**

## Wayfinding operations
- Map: one issue labelled `wayfinder:map`, containing Notes, Decisions-so-far, and Fog.
- Children: GitHub sub-issues labelled `wayfinder:<type>` (`research`, `prototype`, `grilling`, or `task`). If unavailable, use a map task list and `Part of #<map>` in each child.
- Blocking: use native issue dependencies via `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`. Use the blocker's database `.id`, not its issue number or `node_id`. Fall back to `Blocked by: #<n>` when unavailable.
- Frontier: first open child in map order with no assignee and no open blockers. Check `issue_dependencies_summary.blocked_by` or fallback blocker lines.
- Claim: `gh issue edit <n> --add-assignee @me` before work.
- Resolve: comment the answer, close the child, then append a gist and link to the map's Decisions-so-far.
