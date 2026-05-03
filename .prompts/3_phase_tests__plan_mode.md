Our goal is to create integration tests for Phase {N} from `.specs/ai_gen/implementation_plan.md` according to `.specs/ai_gen/testing_strategy.md`. Passing these tests will serve as part of the definition of done for the implementation of this phase, which will be done in a separate session. 

Tests won't be changed during the implementation of the phase.

Before planning:
   - Read `CLAUDE.md`, `.specs/system_spec.md`, `.specs/ai_gen/api_spec.md`, `.specs/ai_gen/db_schema.md`, `.specs/ai_gen/testing_strategy.md`, and `.specs/ai_gen/implementation_plan.md`.
   - Explore the current state of the repo.

During planning:
1. Confirm the planned approach in `.specs/ai_gen/implementation_plan.md` still fits the current codebase. Flag any divergences between the plan and reality. If any, confirm them with the user during planning using `AskUserQuestion` tool and update `.specs/ai_gen/implementation_plan.md` / `CLAUDE.md` to make it consistent with reality.
2. Flag any ambiguities, missing details, or decisions that need to be made before test implementation starts.
3. List the concrete files you will create or modify.
4. List the test deliverables for this phase from the plan and testing strategy and decide on how you'll implement them.
5. Use context7 for any library docs you need.

Final deliverable should be tests in a separate subfolder of the `tests` directory, created according to `.specs/ai_gen/testing_strategy.md`. These tests should fail because the functionality for this phase is yet to be implemented.

After implementation is complete:
   - Review `.gitignore` and add any entries needed to exclude files that should not be version-controlled, based on the languages, frameworks, tools, and build artifacts actually introduced or used in this session (e.g., language-specific caches, dependency directories, build outputs, virtual environments, IDE/editor metadata, OS-generated files, local environment files, test/coverage artifacts). Only add entries that are actually relevant to this repo's stack - do not paste in generic boilerplate. Preserve existing entries; do not remove or reorder them. If `.gitignore` does not exist, create it.
   - [Optional] Make all the required changes in `.specs/ai_gen/*.md` files if during planning you've found any divergences between the plan and current state of the codebase and the user confirmed the changes. These changes must be as pointed as possible and always must be confirmed by the user. 