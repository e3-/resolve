#!/usr/bin/env bash
set -e

# This script assumes it is being run from the "main" branch of your model. Running
# it from another branch may cause errors.

NEW_VERSION=$1
if [ -z "$NEW_VERSION" ]; then
    echo "You must provide the version number you want to use: e.g.:"
    echo "$0 X.Y.Z"
    exit 1
fi

SENTINEL="## UNRELEASED"

if [ $(grep -c "$SENTINEL" CHANGELOG.md) -lt 1 ]; then
    echo "Couldn't find the text '$SENTINEL' in CHANGELOG.md. Please add this and try again."
    exit 1
fi

CURRENT_BRANCH=$(git branch --show-current)
BRANCH_NAME="create-version-$NEW_VERSION"
git checkout -b $BRANCH_NAME

# Update version string in pyproject.toml
sed -i '' "s/version=\".*\"/version=\"$NEW_VERSION\"/" pyproject.toml

# Update CHANGELOG.md:
TODAY=$(date -I)
sed -i '' "s/$SENTINEL/$SENTINEL\n\n## $NEW_VERSION ($TODAY)/" CHANGELOG.md

# Prepare PR:
git add pyproject.toml CHANGELOG.md
git commit -m "Bump version to $NEW_VERSION."
git push -u origin $BRANCH_NAME

open "https://github.com/e3-/kit/compare/$CURRENT_BRANCH...$BRANCH_NAME?expand=1"

git checkout $CURRENT_BRANCH