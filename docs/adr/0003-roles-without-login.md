# Roles without login

Submitter, Reviewer and Admin permissions (including "a Reviewer never approves their own Invoice") are enforced on the server and tested, but the demo picks the role with a switch instead of real sign-in. Login is assumed of a senior engineer and earns little hiring signal; the permission rules are the part that matters for finance. The server asks one question, "who is this and which role?", so adding Cognito later replaces only that answer, not the rules.
