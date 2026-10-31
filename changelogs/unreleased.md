# Unreleased

- Support Lark `user_id` and `union_id` as access-control identifiers. The whitelist accepts session IDs, group IDs, or any sender ID returned by the platform, and the administrator list accepts alias IDs; session IDs and replies continue to use `open_id`. Enable `contact:user.employee_id:readonly` for Lark to return `user_id`.
