#!/usr/bin/env bash
# exit on error
set -o errexit

uv sync --no-dev
uv run prisma generate
uv run prisma py fetch

# Store/pull Prisma cache with build cache
if [[ ! -d $PRISMA_BINARY_CACHE_DIR ]]; then
  echo "...Copying Prisma Binary Cache from Build Cache"
  cp -R $XDG_CACHE_HOME/prisma/binaries $PRISMA_BINARY_CACHE_DIR
else
  echo "...Storing Prisma Binary Cache in Build Cache"
  cp -R $PRISMA_BINARY_CACHE_DIR $XDG_CACHE_HOME
fi