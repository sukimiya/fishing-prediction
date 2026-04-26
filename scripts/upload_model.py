"""Upload trained model to server and trigger reload.

Usage:
    python scripts/upload_model.py                           # upload latest model
    python scripts/upload_model.py --model path/to/model.joblib
    python scripts/upload_model.py --sync-predictor          # also sync predictor.py changes
    python scripts/upload_model.py --no-restart              # skip service restart
"""

import argparse
import subprocess
import sys
from pathlib import Path

SERVER = "root@43.129.205.140"
REMOTE_MODEL_DIR = "/opt/fishpal/module3_prediction_model/models"
REMOTE_INFERENCE_DIR = "/opt/fishpal/module3_prediction_model/inference"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def scp(local: str, remote: str):
    print(f"  Uploading {local} → {remote}")
    result = subprocess.run(
        ["scp", local, f"{SERVER}:{remote}"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"  SCP failed: {result.stderr}")
        return False
    return True


def ssh(command: str) -> bool:
    print(f"  SSH: {command}")
    result = subprocess.run(
        ["ssh", SERVER, command],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"  SSH failed: {result.stderr}")
        return False
    if result.stdout.strip():
        print(f"  Output: {result.stdout.strip()}")
    return True


def upload_model(model_path: str, no_restart: bool = False):
    print(f"Uploading model to {SERVER}...")

    local_model = Path(model_path)
    if not local_model.exists():
        print(f"Model not found: {local_model}")
        print("Run training first: python -m module3_prediction_model.training.train_model")
        return False

    # Ensure remote dir exists
    ssh(f"mkdir -p {REMOTE_MODEL_DIR}")

    # Upload model file
    remote_path = f"{REMOTE_MODEL_DIR}/{local_model.name}"
    if not scp(str(local_model), remote_path):
        return False

    # Upload metadata if exists
    meta_local = local_model.parent / "model_metadata.json"
    if meta_local.exists():
        scp(str(meta_local), f"{REMOTE_MODEL_DIR}/model_metadata.json")

    if no_restart:
        print("Model uploaded (--no-restart, service not restarted)")
        return True

    # Restart service
    print("Restarting fishpal service...")
    if not ssh("systemctl restart fishpal"):
        print("WARNING: Restart failed, try manually: ssh root@43.129.205.140 'systemctl restart fishpal'")
        return False

    # Verify
    time.sleep(2)
    result = subprocess.run(
        ["ssh", SERVER, "systemctl is-active fishpal"],
        capture_output=True, text=True, timeout=10,
    )
    status = result.stdout.strip()
    if status == "active":
        print(f"FishPal service restarted: {status}")
        return True
    else:
        print(f"WARNING: Service status: {status}")
        return False


def sync_predictor(no_restart: bool = False):
    """Sync predictor.py changes to server."""
    print("Syncing predictor.py to server...")

    local_predictor = PROJECT_ROOT / "module3_prediction_model" / "inference" / "predictor.py"
    if not local_predictor.exists():
        print(f"predictor.py not found: {local_predictor}")
        return False

    ssh(f"mkdir -p {REMOTE_INFERENCE_DIR}")
    if not scp(str(local_predictor), f"{REMOTE_INFERENCE_DIR}/predictor.py"):
        return False

    if no_restart:
        print("Predictor synced (--no-restart, service not restarted)")
        return True

    ssh("systemctl restart fishpal")
    print("Predictor synced and service restarted.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Upload model to server")
    parser.add_argument("--model", "-m", default=str(PROJECT_ROOT / "module3_prediction_model" / "models" / "fishing_model.joblib"),
                        help="Path to model.joblib")
    parser.add_argument("--sync-predictor", "-p", action="store_true",
                        help="Also sync predictor.py to server")
    parser.add_argument("--no-restart", "-n", action="store_true",
                        help="Skip service restart")
    args = parser.parse_args()

    success = True

    if args.sync_predictor:
        if not sync_predictor(no_restart=args.no_restart):
            success = False

    if not upload_model(args.model, no_restart=args.no_restart):
        success = False

    if success:
        print("\nDone! Model deployment complete.")
    else:
        print("\nDeployment had issues. Check the output above.")
        sys.exit(1)


if __name__ == "__main__":
    import time
    main()
