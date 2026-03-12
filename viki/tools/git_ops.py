import os
import subprocess
from pathlib import Path
from typing import Optional, List
from .._log import structlog

logger = structlog.get_logger()

class GitOperator:
    """Git operations wrapper"""
    
    def __init__(self, workspace_path: str = "."):
        self.workspace = Path(workspace_path)
        self._git_available = self._check_git()
    
    def _check_git(self) -> bool:
        """Check if git is available"""
        try:
            subprocess.run(["git", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def is_repo(self) -> bool:
        """Check if workspace is a git repo"""
        if not self._git_available:
            return False
        git_dir = self.workspace / ".git"
        return git_dir.exists()
    
    def init(self):
        """Initialize git repo"""
        if not self._git_available:
            logger.warning("Git not available")
            return
        try:
            subprocess.run(
                ["git", "init"],
                cwd=self.workspace,
                capture_output=True,
                check=True
            )
            logger.info(f"Initialized git repo at {self.workspace}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Git init failed: {e}")
    
    def checkout_branch(self, branch_name: str):
        """Create and checkout a new branch"""
        if not self._git_available:
            return
        try:
            # Create branch
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.workspace,
                capture_output=True,
                check=True
            )
            logger.info(f"Created branch: {branch_name}")
        except subprocess.CalledProcessError:
            # Branch might exist, try to checkout
            try:
                subprocess.run(
                    ["git", "checkout", branch_name],
                    cwd=self.workspace,
                    capture_output=True,
                    check=True
                )
            except subprocess.CalledProcessError as e:
                logger.error(f"Git checkout failed: {e}")
    
    def get_head_hash(self) -> str:
        """Get current HEAD commit hash"""
        if not self._git_available:
            return ""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return ""
    
    def add(self, files: List[str]):
        """Stage files"""
        if not self._git_available:
            return
        try:
            subprocess.run(
                ["git", "add"] + files,
                cwd=self.workspace,
                capture_output=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Git add failed: {e}")
    
    def commit(self, message: str):
        """Commit staged changes"""
        if not self._git_available:
            return
        try:
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.workspace,
                capture_output=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Git commit failed: {e}")
    
    def get_diff(self) -> str:
        """Get diff of uncommitted changes"""
        if not self._git_available:
            return ""
        try:
            result = subprocess.run(
                ["git", "diff"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError:
            return ""
