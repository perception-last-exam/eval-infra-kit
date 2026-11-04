#!/usr/bin/env bash
# usage: run_pipeline.sh <scene_id> <variant> <gpu>
# solver (fresh codex session, only input.mp4 in its folder) -> one fresh judge session per query.
# Codex runs in its workspace-write sandbox (writes only inside its own folder), network on for installs.
set -u
KIT=$(cd "$(dirname "$0")/.." && pwd)
R=${R2S_RUNS:-$KIT/../round2-runs}
K=$KIT/prompts/round2
EXAMPLES=${R2S_EXAMPLES:-$KIT/../registry-demo/_examples}
SCENE=$1; V=$2; GPU=$3
SJ=$(ls $EXAMPLES/*/$SCENE/scene.json)
D=$R/$SCENE/$V; RUN=$D/solver; LOG=$D/logs
mkdir -p $RUN $LOG
cp $R/_videos/$SCENE.mp4 $RUN/input.mp4
python3 $K/prompts.py solver --variant $V --scene $SJ > $LOG/solver-prompt.md
export PATH=$R/_bin:$PATH CUDA_VISIBLE_DEVICES=$GPU
SANDBOX=(-s workspace-write -c sandbox_workspace_write.network_access=true)
cd $RUN
date -Is > $LOG/solver.start
timeout 5h codex exec --json --skip-git-repo-check "${SANDBOX[@]}" \
  -m gpt-6.1-sol -c model_reasoning_effort=max -o $LOG/solver.last.md "$(cat $LOG/solver-prompt.md)" \
  > $LOG/solver.jsonl 2> $LOG/solver.stderr
echo $? > $LOG/solver.exit; date -Is > $LOG/solver.end
for QP in $R/$SCENE/judge-prompts/*.md; do
  Q=$(basename $QP .md); J=$D/judge/$Q; mkdir -p $J
  [ -d $RUN/output ] && cp -r $RUN/output $J/submission
  cp $QP $LOG/judge-$Q-prompt.md
  ( cd $J && timeout 2h codex exec --json --skip-git-repo-check "${SANDBOX[@]}" \
      -m gpt-6.1-sol -c model_reasoning_effort=max -o $LOG/judge-$Q.last.md "$(cat $QP)" \
      > $LOG/judge-$Q.jsonl 2> $LOG/judge-$Q.stderr; echo $? > $LOG/judge-$Q.exit ) &
done
wait
date -Is > $LOG/done
