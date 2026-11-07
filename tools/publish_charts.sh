#!/usr/bin/env bash
# 서버가 그린 그림(static/charts)을 charts 가지에 한 커밋으로 올린다(늘 덮어써서 기록이 쌓이지 않는다).
set -eu
repo_url="https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
tmp=$(mktemp -d)
cp static/charts/* "$tmp"/
cd "$tmp"
git init -q -b charts
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A
git commit -q -m "그림 $(TZ=Asia/Seoul date +%F) (서버, LibreOffice)"
git push -q -f "$repo_url" charts
echo "charts 가지에 그림 $(ls | wc -l)개 올림"
