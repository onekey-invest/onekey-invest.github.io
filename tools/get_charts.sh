#!/usr/bin/env bash
# 서버가 그린 그림(charts 가지)을 static/charts에 덮어 놓는다. 없으면 저장소의 그림을 그대로 쓴다.
# 매일 실행이 그림을 그려 charts 가지에 올리고, 다른 배포(푸시·장중)는 이것으로 같은 그림을 쓴다.
set -u
if git fetch -q --depth 1 origin charts 2>/dev/null; then
  git archive FETCH_HEAD | tar -x -C static/charts
  echo "charts 가지의 그림 $(git ls-tree --name-only FETCH_HEAD | wc -l)개를 씀"
else
  echo "charts 가지가 없다. 저장소의 그림을 씀"
fi
