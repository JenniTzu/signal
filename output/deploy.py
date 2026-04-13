# ═══════════════════════════════════════════════════════════
# SIGNAL — deploy.py
# 推送 docs/ 資料夾到 GitHub Pages
# ═══════════════════════════════════════════════════════════

import sys
import subprocess
import os
import shutil
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import config


def run_git(args: list, cwd: str = None) -> tuple[int, str, str]:
    """執行 git 指令，回傳 (returncode, stdout, stderr)"""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd or os.path.dirname(__file__),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def deploy_to_github(commit_message: str = "auto: daily update") -> dict:
    """將 docs/ 推送到 GitHub（透過 git + token in URL）"""
    print("\n【deploy.py】推送 GitHub Pages...")

    # 重新讀取（確保取到最新環境變數）
    token = os.environ.get("SIGNAL_GITHUB_TOKEN", "") or config.GITHUB_TOKEN
    repo  = config.GITHUB_REPO

    if not token or not repo:
        print("  ⓘ GITHUB_TOKEN 或 GITHUB_REPO 未設定，跳過部署")
        return {"success": False, "message": "GitHub 設定未完成（待設定）", "skipped": True}

    repo_dir    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    remote_url  = f"https://{token}@github.com/{repo}.git"
    owner       = repo.split("/")[0]
    repo_name   = repo.split("/")[-1]
    site_url    = f"https://{owner}.github.io/{repo_name}/"

    # 設定/更新 remote（含 token）
    run_git(["remote", "set-url", "origin", remote_url], cwd=repo_dir)

    # 設定 git user（避免 CI 環境沒有設定）
    run_git(["config", "user.email", "signal-bot@auto.com"], cwd=repo_dir)
    run_git(["config", "user.name",  "SIGNAL Bot"],          cwd=repo_dir)

    # 複製回測結果到 docs/（供網站讀取）
    bt_src = os.path.join(repo_dir, "cache", "backtest_results.json")
    bt_dst = os.path.join(repo_dir, "docs",  "backtest.json")
    if os.path.exists(bt_src):
        shutil.copy2(bt_src, bt_dst)

    # Stage docs/
    run_git(["add", "docs/data.json", "docs/index.html", "docs/backtest.json"], cwd=repo_dir)

    # Commit（沒有變更也允許）
    code, out, err = run_git(
        ["commit", "-m", commit_message, "--allow-empty"],
        cwd=repo_dir
    )
    if code != 0 and "nothing to commit" not in (out + err):
        print(f"  Commit 訊息：{out or err}")

    # Push
    code, out, err = run_git(["push", "origin", "main"], cwd=repo_dir)
    if code == 0:
        print(f"  推送成功！網站：{site_url}")
        return {"success": True, "message": "推送成功", "url": site_url}
    else:
        print(f"  Push 失敗：{err[:200]}")
        return {"success": False, "message": err[:200]}


if __name__ == "__main__":
    result = deploy_to_github("test: manual deploy")
    print(result)
