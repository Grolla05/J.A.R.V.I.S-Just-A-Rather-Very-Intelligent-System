Você traduz um pedido sobre o GitHub em uma ação. Responda APENAS um JSON.

Ações possíveis:
- "open_prs": listar pull requests abertos de um repositório.
- "issues": listar issues abertas atribuídas ao usuário.
- "last_commit": mostrar o último commit de um repositório.
- "ci": mostrar o status do CI / GitHub Actions de um repositório.
- "create_issue": criar uma issue (extraia "title" curto e "body" opcional).

Repositório padrão do usuário: $default_repo
Se o pedido citar um repositório no formato dono/repo, use em "repo"; senão use null.

Schema:
{"action": "open_prs|issues|last_commit|ci|create_issue", "repo": "dono/repo" ou null, "title": "..." ou null, "body": "..." ou null}

Pedido: "$command"
