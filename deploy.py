#!/usr/bin/env python3
"""
Terraform lifecycle manager for the weather station infrastructure.

Usage:
  python3 deploy.py --env ENV --stage STAGE --action ACTION [--auto-approve]

  ENV    : dev | staging | prod
  STAGE  : 0 | 1 | 2 | all
  ACTION : init | plan | apply | destroy | output | validate

Examples:
  python3 deploy.py --env dev --stage 0   --action apply   # bootstraps S3 state bucket
  python3 deploy.py --env dev --stage all --action apply --auto-approve
  python3 deploy.py --env dev --stage 1   --action plan

Stage 0 bootstrap:
  1. Applies with local backend (S3 bucket doesn't exist yet)
  2. Migrates stage 0 state into the newly created S3 bucket
  Subsequent stage 0 applies use the S3 backend normally.

Stages 1–2:
  Fresh init against the S3 bucket (created by stage 0).
  No migration — state is written to S3 on first apply.
"""

import argparse
import os
import subprocess
import sys

import boto3

PROJECT = "weather-station"
STAGES  = [0, 1, 2]

ROOT  = os.path.dirname(os.path.abspath(__file__))
INFRA = os.path.join(ROOT, "infrastructure")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sdir(stage: int) -> str:
    return os.path.join(INFRA, f"stage{stage}")


def run(cmd: list, cwd: str) -> None:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        sys.exit(result.returncode)


def get_region() -> str:
    region = boto3.session.Session().region_name
    if not region:
        sys.exit("ERROR: no AWS region configured — set AWS_DEFAULT_REGION or configure a profile region")
    return region


def get_account_id() -> str:
    return boto3.client("sts").get_caller_identity()["Account"]


def remote_bucket(account_id: str) -> str:
    return f"{PROJECT}-{account_id}-tfstate"


def state_key(env: str, stage: int) -> str:
    if stage == 0:
        return "global/stage0/terraform.tfstate"
    return f"{env}/stage{stage}/terraform.tfstate"


def write_backend_cfg(env: str, stage: int, bucket: str, region: str) -> str:
    """Write a backend.<env>.hcl to the stage directory and return its path."""
    path = os.path.join(sdir(stage), f"backend.{env}.hcl")
    with open(path, "w") as f:
        f.write(
            f'bucket       = "{bucket}"\n'
            f'key          = "{state_key(env, stage)}"\n'
            f'region       = "{region}"\n'
            f'use_lockfile = true\n'
            f'encrypt      = true\n'
        )
    return path


def env_vars(env: str, stage: int) -> list:
    """Return -var flags for the given stage. Stage 0 has no environment variable."""
    if stage == 0:
        return []
    return [f"-var=environment={env}"]


# ---------------------------------------------------------------------------
# Action runners
# ---------------------------------------------------------------------------

def do_init(stage: int, backend_cfg: str) -> None:
    cmd = ["terraform", "init", f"-backend-config={backend_cfg}", "-reconfigure"]
    print(f"\n$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=sdir(stage), input=b"no\n")
    if result.returncode != 0:
        sys.exit(result.returncode)


def do_plan(stage: int, evars: list) -> None:
    run(["terraform", "plan"] + evars, sdir(stage))


def do_apply(stage: int, evars: list, auto_approve: bool) -> None:
    cmd = ["terraform", "apply"] + evars
    if auto_approve:
        cmd.append("-auto-approve")
    run(cmd, sdir(stage))


def do_destroy(stage: int, evars: list, auto_approve: bool) -> None:
    cmd = ["terraform", "destroy"] + evars
    if auto_approve:
        cmd.append("-auto-approve")
    run(cmd, sdir(stage))


_BOOTSTRAP_OVERRIDE = """\
# Written by deploy.py during stage-0 bootstrap — removed automatically.
# Overrides backend "s3" {} so the initial apply can run before the bucket exists.
terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}
"""


def _s3_bucket_exists(bucket: str) -> bool:
    try:
        boto3.client("s3").head_bucket(Bucket=bucket)
        return True
    except Exception:
        return False


def bootstrap_stage0(backend_cfg: str, bucket: str, evars: list, auto_approve: bool) -> None:
    """
    Handle the chicken-and-egg for stage 0: the S3 backend bucket doesn't exist
    until after the first apply.

    Decision tree (checked in order):
      1. Bucket exists + no local state  →  normal S3 init + apply (ongoing).
      2. Bucket exists + local state     →  migration was interrupted; re-init
                                            with local backend then migrate.
      3. Bucket absent                   →  full bootstrap: local-backend apply
                                            (creates bucket), then migrate.
    """
    import shutil

    dot_tf      = os.path.join(sdir(0), ".terraform")
    local_state = os.path.join(sdir(0), "terraform.tfstate")
    override    = os.path.join(sdir(0), "bootstrap_override.tf")

    if _s3_bucket_exists(bucket) and not os.path.exists(local_state):
        print("Stage 0: state bucket found — reinitialising and applying...")
        do_init(0, backend_cfg)
        do_apply(0, evars, auto_approve)
        return

    if os.path.exists(dot_tf):
        print("Stage 0: clearing stale .terraform for bootstrap/migration...")
        shutil.rmtree(dot_tf)

    try:
        with open(override, "w") as fh:
            fh.write(_BOOTSTRAP_OVERRIDE)

        if os.path.exists(local_state):
            print("Stage 0: local state found — setting up for migration...")
            run(["terraform", "init", "-reconfigure"], sdir(0))
        else:
            print("Stage 0 bootstrap: initialising with local backend for first apply...")
            run(["terraform", "init", "-reconfigure"], sdir(0))
            do_apply(0, evars, auto_approve)
    finally:
        if os.path.exists(override):
            os.remove(override)

    print("\nStage 0: migrating state to S3...")
    run(["terraform", "init", "-migrate-state", "-force-copy",
         f"-backend-config={backend_cfg}"], sdir(0))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--env",          required=True, choices=["dev", "staging", "prod"])
    p.add_argument("--stage",        required=True, metavar="STAGE", help="0 | 1 | 2 | all")
    p.add_argument("--action",       required=True,
                   choices=["init", "plan", "apply", "destroy", "output", "validate"])
    p.add_argument("--auto-approve", action="store_true",
                   help="Pass -auto-approve to apply/destroy (non-interactive)")
    args = p.parse_args()

    if args.stage == "all":
        stages = list(reversed(STAGES)) if args.action == "destroy" else STAGES
    else:
        try:
            n = int(args.stage)
            if n not in STAGES:
                raise ValueError
            stages = [n]
        except ValueError:
            p.error(f"--stage must be 0, 1, 2, or 'all', got {args.stage!r}")

    try:
        region     = get_region()
        account_id = get_account_id()
        bucket     = remote_bucket(account_id)
        print(f"AWS account: {account_id}  region: {region}  state bucket: {bucket}")
    except Exception as exc:
        sys.exit(f"ERROR: cannot resolve AWS identity — {exc}")

    for stage in stages:
        print(f"\n{'='*56}")
        print(f"  env={args.env}  stage={stage}  action={args.action}")
        print(f"{'='*56}")

        backend_cfg = write_backend_cfg(args.env, stage, bucket, region)
        evars       = env_vars(args.env, stage)

        if args.action == "validate":
            pass  # no backend needed
        elif stage == 0 and args.action == "apply":
            pass  # bootstrap_stage0 handles init internally
        else:
            do_init(stage, backend_cfg)

        if args.action == "init":
            pass  # init already ran above

        elif args.action == "plan":
            if stage == 0 and not _s3_bucket_exists(bucket):
                import shutil
                dot_tf   = os.path.join(sdir(0), ".terraform")
                override = os.path.join(sdir(0), "bootstrap_override.tf")
                if os.path.exists(dot_tf):
                    shutil.rmtree(dot_tf)
                try:
                    with open(override, "w") as fh:
                        fh.write(_BOOTSTRAP_OVERRIDE)
                    run(["terraform", "init", "-reconfigure"], sdir(0))
                    do_plan(0, evars)
                finally:
                    if os.path.exists(override):
                        os.remove(override)
            else:
                do_plan(stage, evars)

        elif args.action == "apply":
            if stage == 0:
                bootstrap_stage0(backend_cfg, bucket, evars, args.auto_approve)
            else:
                do_apply(stage, evars, args.auto_approve)

        elif args.action == "destroy":
            do_destroy(stage, evars, args.auto_approve)

        elif args.action == "output":
            run(["terraform", "output"], sdir(stage))

        elif args.action == "validate":
            run(["terraform", "validate"], sdir(stage))

    print(f"\nDone: env={args.env}  stage={args.stage}  action={args.action}")


if __name__ == "__main__":
    main()
