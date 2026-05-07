#!/usr/bin/env bash
set -euo pipefail

# Compose runtime: "docker compose" or "podman compose". Override with
#   COMPOSE="podman compose" ./run-all-tests.sh
COMPOSE="${COMPOSE:-docker compose}"

PHASES=(
  phase-1-infra
  phase-2-db
  phase-3-auth
  phase-4-products
  phase-5-recipes
  phase-6-listing
  phase-7-shopping-list
  phase-8-frontend-products
  phase-9-frontend-recipes-and-shopping
  phase-10-e2e
)

KEEP_GOING=0
if [[ "${1:-}" == "--keep-going" ]]; then
  KEEP_GOING=1
fi

failed=()

for phase in "${PHASES[@]}"; do
  echo "=== $phase ==="
  pushd "tests/$phase" >/dev/null

  $COMPOSE up -d --wait

  if uv run pytest -v ; then
    echo "PASS: $phase"
  else
    echo "FAIL: $phase"
    failed+=("$phase")
  fi

  $COMPOSE down -v
  popd >/dev/null

  if [[ ${#failed[@]} -gt 0 && $KEEP_GOING -eq 0 ]]; then
    echo "Stopping at first failure. Use --keep-going to continue."
    break
  fi
done

if [[ ${#failed[@]} -gt 0 ]]; then
  echo "Failed phases: ${failed[*]}"
  exit 1
fi

echo "All phases passed."
