## Summary

<!-- 1-3 bullet points describing what this PR does -->

- 

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / cleanup
- [ ] Documentation
- [ ] Infrastructure / CI

## Test plan

<!-- How did you verify this works? What edge cases did you check? -->

- [ ] `pytest tests/ -v` passes
- [ ] `npm run build` passes
- [ ] Manually tested the golden path in a browser
- [ ] 

## Security checklist

<!-- Check all that apply. If a box isn't relevant, leave it unchecked. -->

- [ ] No user input is used as a file path without going through `user_path()`
- [ ] New brain file writes use `write_json()` / `write_markdown()` (not `open(..., 'w')`)
- [ ] AI prompt injection: any user-controlled content injected into prompts is wrapped in `<brain_data>` tags
- [ ] No secrets or credentials committed

## Breaking changes

<!-- List any API or behavior changes that could affect existing deployments. -->

None / ...
