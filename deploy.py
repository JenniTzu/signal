# ═══════════════════════════════════════════════════════════
# SIGNAL — deploy.py
# 推送 docs/ 資料夾到 GitHub Pages
# ═══════════════════════════════════════════════════════════

import subprocess
import os
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
    """將 docs/ 推送到 GitHub"""
    print("\n【deploy.py】推送 GitHub Pages...")

    if not config.GITHUB_TOKEN or not config.GITHUB_REPO:
        print("  ⓘ GITHUB_TOKEN 或 GITHUB_REPO 未設定，跳過部署")
        return {
            "success": False,
            "message": "GitHub 設定未完成（待設定）",
            "skipped": True,
        }

    repo_dir = os.path.dirname(__file__)

    # 確認 git 環境
    code, out, err = run_git(["status", "--short"], cwd=repo_dir)
    if code != 0:
        # 初始化 repo
        print("  初始化 git repo...")
        run_git(["init"], cwd=repo_dir)
        run_git(["branch", "-M", "main"], cwd=repo_dir)

        # 設定 remote
        remote_url = (
            f"https://{config.GITHUB_TOKEN}@github.com/"
            f"{config.GITHUB_REPO}.git"
        )
        run_git(["remote", "add", "origin", remote_url], cwd=repo_dir)

    # Stage docs/
    run_git(["add", "docs/"], cwd=repo_dir)

    # Commit
    code, out, err = run_git(
        ["commit", "-m", commit_message, "--allow-empty"],
        cwd=repo_dir
    )
    if code != 0 and "nothing to commit" not in err and "nothing to commit" not in out:
        print(f"  ⚠️  Commit 失敗：{err}")
        return {"success": False, "message": err}

    # Push
    code, out, err = run_git(
        ["push", "origin", "main", "--force"],
        cwd=repo_dir
    )
    if code == 0:
        repo_name = config.GITHUB_REPO.split("/")[-1]
        owner     = config.GITHUB_REPO.split("/")[0]
        url       = f"https://{owner}.github.io/{repo_name}/"
        print(f"  ✅ 推送成功！網站：{url}")
        return {"success": True, "message": "推送成功", "url": url}
    else:
        print(f"  ⚠️  Push 失敗：{err}")
        return {"success": False, "message": err}


if __name__ == "__main__":
    result = deploy_to_github("test: manual deploy")
    print(result)
