Our goal is to implement Phase {N} from `.specs/implementation_plan.md`. The integration tests for this phase already exist under `tests/` (created in a previous session) and must not be modified, skipped, or deleted. Passing all of these tests — and not regressing any tests from earlier phases — is an essential part of the definition of done for this phase. No additional tests (unit tests, extra integration tests, smoke tests, etc.) should be created.

Before planning:
   - Read `CLAUDE.md`, `.specs/system_spec.md`, `.specs/api_spec.md`, `.specs/db_schema.md`, `.specs/testing_strategy.md`, and `.specs/implementation_plan.md`.
   - Locate and read the existing integration tests for Phase {N} under `tests/`.
   - Explore the current state of the repo, including any code from earlier phases this phase builds on.

During planning:
1. Confirm the planned approach in `.specs/ai_gen/implementation_plan.md` still fits the current codebase. Flag any divergences between the plan and reality. If any, confirm them with the user during planning using `AskUserQuestion` tool and update `.specs/ai_gen/implementation_plan.md` / `CLAUDE.md` to make it consistent with reality.
2. Confirm the existing Phase {N} integration tests are consistent with the plan and the specs. Flag any contradictions, gaps, or tests that appear to encode requirements not present in the specs. Surface these to the user before proceeding — do not modify the tests unilaterally.
3. Flag any ambiguities, missing details, or decisions that need to be made before implementation starts.
4. List the concrete files you will create or modify.
5. List the implementation deliverables for this phase from the plan and map each one to the tests it must satisfy. Identify any deliverable that is not currently covered by a test and surface it to the user.
6. Use context7 for any library docs you need.

Final deliverable should be a working implementation of Phase {N} such that:
   - All existing Phase {N} integration tests pass.
   - All tests from earlier phases continue to pass (no regressions).
   - No existing tests are modified, skipped, or deleted.
   - No new tests are added.
   - The code conforms to `CLAUDE.md` and phase specification.


After implementation is complete:
   - Review `.gitignore` and add any entries needed to exclude files that should not be version-controlled, based on the languages, frameworks, tools, and build artifacts actually introduced or used in this session (e.g., language-specific caches, dependency directories, build outputs, virtual environments, IDE/editor metadata, OS-generated files, local environment files, test/coverage artifacts). Only add entries that are actually relevant to this repo's stack - do not paste in generic boilerplate. Preserve existing entries; do not remove or reorder them. If `.gitignore` does not exist, create it.
   - [Optional] Make all the required changes in `.specs/ai_gen/*.md` files if during planning you've found any divergences between the plan and current state of the codebase and the user confirmed the changes. These changes must be as pointed as possible and always must be confirmed by the user. 