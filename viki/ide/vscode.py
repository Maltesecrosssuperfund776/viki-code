from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


class VSCodeIntegrator:
    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()
        self.vscode_dir = self.workspace / ".vscode"
        self.extension_dir = self.workspace / ".viki-workspace" / "ide" / "vscode-extension"

    def install(self) -> Dict[str, str]:
        self.vscode_dir.mkdir(parents=True, exist_ok=True)
        files = {
            "settings.json": {
                "python.testing.pytestEnabled": True,
                "python.testing.pytestArgs": ["tests"],
                "editor.formatOnSave": True,
                "editor.codeActionsOnSave": {"source.fixAll": "explicit"},
                "files.exclude": {"**/.viki-workspace": True},
                "diffEditor.renderSideBySide": True,
                "scm.diffDecorations": "all",
                "testing.automaticallyOpenPeekView": "never",
                "viki.apiBaseUrl": "http://127.0.0.1:8787",
            },
            "tasks.json": {
                "version": "2.0.0",
                "tasks": [
                    {"label": "VIKI: doctor", "type": "shell", "command": "viki doctor"},
                    {"label": "VIKI: tests", "type": "shell", "command": "python -m pytest -q"},
                    {"label": "VIKI: tui", "type": "shell", "command": "viki tui"},
                    {"label": "VIKI: approvals", "type": "shell", "command": "viki approvals list"},
                    {"label": "VIKI: resume", "type": "shell", "command": "viki resume"},
                    {"label": "VIKI: benchmark", "type": "shell", "command": "viki evals run"},
                    {"label": "VIKI: symbols", "type": "shell", "command": "viki symbols \"auth\" --path ."},
                    {"label": "VIKI: impact", "type": "shell", "command": "viki impact --changed-file viki/api/server.py --path ."},
                ],
            },
            "extensions.json": {
                "recommendations": [
                    "ms-python.python",
                    "ms-python.vscode-pylance",
                    "charliermarsh.ruff",
                    "github.vscode-github-actions",
                    "eamodio.gitlens",
                ]
            },
            "launch.json": {
                "version": "0.2.0",
                "configurations": [
                    {
                        "name": "VIKI API server",
                        "type": "python",
                        "request": "launch",
                        "module": "viki.cli",
                        "args": ["up"],
                        "console": "integratedTerminal",
                    }
                ],
            },
        }
        written = {}
        for name, payload in files.items():
            path = self.vscode_dir / name
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            written[name] = str(path)
        return written

    def install_extension_scaffold(self) -> Dict[str, str]:
        self.extension_dir.mkdir(parents=True, exist_ok=True)
        package_json = {
            "name": "viki-code-assistant",
            "displayName": "VIKI Code Assistant",
            "version": "0.2.0",
            "publisher": "rebootix",
            "engines": {"vscode": "^1.90.0"},
            "activationEvents": [
                "onCommand:viki.submitTask",
                "onCommand:viki.refreshSessions",
                "onCommand:viki.taskStatus",
                "onCommand:viki.previewDiff",
                "onCommand:viki.approveChange",
                "onCommand:viki.rejectChange",
                "onCommand:viki.repoSearch",
                "onCommand:viki.symbolLookup",
                "onCommand:viki.showLogs",
            ],
            "main": "./extension.js",
            "contributes": {
                "viewsContainers": {
                    "activitybar": [
                        {
                            "id": "viki",
                            "title": "VIKI",
                            "icon": "media/viki.svg",
                        }
                    ]
                },
                "views": {
                    "viki": [
                        {"id": "vikiSessions", "name": "Sessions"},
                        {"id": "vikiApprovals", "name": "Approvals"},
                    ]
                },
                "commands": [
                    {"command": "viki.submitTask", "title": "VIKI: Submit Task"},
                    {"command": "viki.refreshSessions", "title": "VIKI: Refresh Sessions"},
                    {"command": "viki.taskStatus", "title": "VIKI: Task Status"},
                    {"command": "viki.previewDiff", "title": "VIKI: Preview Diff"},
                    {"command": "viki.approveChange", "title": "VIKI: Approve Change"},
                    {"command": "viki.rejectChange", "title": "VIKI: Reject Change"},
                    {"command": "viki.repoSearch", "title": "VIKI: Repo Search"},
                    {"command": "viki.symbolLookup", "title": "VIKI: Symbol Lookup"},
                    {"command": "viki.showLogs", "title": "VIKI: Show Logs"},
                ]
            },
        }
        extension_js = """
const vscode = require('vscode');
const cp = require('child_process');
const http = require('http');

function workspaceRoot() {
  const folder = vscode.workspace.workspaceFolders?.[0];
  return folder ? folder.uri.fsPath : process.cwd();
}

function apiBase() {
  return vscode.workspace.getConfiguration().get('viki.apiBaseUrl', 'http://127.0.0.1:8787');
}

function cli(args) {
  return new Promise((resolve, reject) => {
    cp.execFile('viki', args, { cwd: workspaceRoot(), maxBuffer: 10 * 1024 * 1024 }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(stderr || stdout || error.message));
        return;
      }
      resolve(stdout.trim());
    });
  });
}

function api(path) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, apiBase());
    const req = http.get(url, (res) => {
      let body = '';
      res.on('data', (chunk) => body += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(body || '{}'));
        } catch (error) {
          reject(error);
        }
      });
    });
    req.on('error', reject);
  });
}

class SimpleTreeProvider {
  constructor(loader) {
    this.loader = loader;
    this._onDidChangeTreeData = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._onDidChangeTreeData.event;
  }

  refresh() {
    this._onDidChangeTreeData.fire();
  }

  async getChildren() {
    const items = await this.loader();
    return items.map((item) => new vscode.TreeItem(item.label));
  }

  getTreeItem(item) {
    return item;
  }
}

function activate(context) {
  const output = vscode.window.createOutputChannel('VIKI');
  const sessions = new SimpleTreeProvider(async () => {
    try {
      const payload = await api('/runs?limit=5');
      return (payload.items || []).map((item) => ({ label: `${item.id} | ${item.status || '?'}` }));
    } catch {
      return [{ label: 'Start `viki up .` to load sessions' }];
    }
  });
  const approvals = new SimpleTreeProvider(async () => {
    try {
      const payload = await api('/approvals?status=pending');
      return (payload.items || []).slice(0, 5).map((item) => ({ label: `#${item.id} | ${item.subject}` }));
    } catch {
      return [{ label: 'API unavailable' }];
    }
  });

  context.subscriptions.push(vscode.window.registerTreeDataProvider('vikiSessions', sessions));
  context.subscriptions.push(vscode.window.registerTreeDataProvider('vikiApprovals', approvals));

  async function showJson(title, payload) {
    const doc = await vscode.workspace.openTextDocument({ language: 'json', content: JSON.stringify(payload, null, 2) });
    await vscode.window.showTextDocument(doc, { preview: false });
    output.appendLine(`[${title}] opened`);
  }

  context.subscriptions.push(vscode.commands.registerCommand('viki.submitTask', async () => {
    const prompt = await vscode.window.showInputBox({ prompt: 'Run a VIKI task' });
    if (!prompt) { return; }
    const terminal = vscode.window.createTerminal('VIKI');
    terminal.show();
    terminal.sendText(`viki run "${prompt.replace(/"/g, '\\"')}" --path .`);
    sessions.refresh();
    approvals.refresh();
  }));

  context.subscriptions.push(vscode.commands.registerCommand('viki.refreshSessions', async () => {
    sessions.refresh();
    approvals.refresh();
    vscode.window.showInformationMessage('VIKI views refreshed.');
  }));

  context.subscriptions.push(vscode.commands.registerCommand('viki.taskStatus', async () => {
    const sessionId = await vscode.window.showInputBox({ prompt: 'Session id' });
    if (!sessionId) { return; }
    const payload = JSON.parse(await cli(['status', '.', '--session-id', sessionId]));
    await showJson('status', payload);
  }));

  context.subscriptions.push(vscode.commands.registerCommand('viki.previewDiff', async () => {
    const sessionId = await vscode.window.showInputBox({ prompt: 'Session id for diff preview' });
    if (!sessionId) { return; }
    const payload = JSON.parse(await cli(['diff', sessionId, '--path', '.']));
    await showJson('diff', payload);
  }));

  context.subscriptions.push(vscode.commands.registerCommand('viki.approveChange', async () => {
    const approvalId = await vscode.window.showInputBox({ prompt: 'Approval id to approve' });
    if (!approvalId) { return; }
    await cli(['approvals', 'approve', approvalId, '.']);
    approvals.refresh();
    vscode.window.showInformationMessage(`Approved #${approvalId}`);
  }));

  context.subscriptions.push(vscode.commands.registerCommand('viki.rejectChange', async () => {
    const approvalId = await vscode.window.showInputBox({ prompt: 'Approval id to reject' });
    if (!approvalId) { return; }
    await cli(['approvals', 'reject', approvalId, '.']);
    approvals.refresh();
    vscode.window.showInformationMessage(`Rejected #${approvalId}`);
  }));

  context.subscriptions.push(vscode.commands.registerCommand('viki.repoSearch', async () => {
    const query = await vscode.window.showInputBox({ prompt: 'Repo search query' });
    if (!query) { return; }
    const payload = JSON.parse(await cli(['repo', query, '--path', '.']));
    await showJson('repo', payload);
  }));

  context.subscriptions.push(vscode.commands.registerCommand('viki.symbolLookup', async () => {
    const query = await vscode.window.showInputBox({ prompt: 'Symbol search query' });
    if (!query) { return; }
    const payload = JSON.parse(await cli(['symbols', query, '--path', '.']));
    await showJson('symbols', payload);
  }));

  context.subscriptions.push(vscode.commands.registerCommand('viki.showLogs', async () => {
    const sessionId = await vscode.window.showInputBox({ prompt: 'Session id for logs' });
    if (!sessionId) { return; }
    const payload = await api(`/runs/${sessionId}/result`);
    await showJson('logs', payload);
  }));
}

function deactivate() {}

module.exports = { activate, deactivate };
""".strip() + "\n"
        readme = "# VIKI VS Code Extension\n\nThis extension talks to the local VIKI CLI and API to submit tasks, inspect sessions, preview diffs, manage approvals, search the repo, look up symbols, and inspect logs.\n\n## Usage\n\n1. Start the local API with `viki up .`\n2. Open the Command Palette and run `VIKI: Submit Task`\n3. Use the VIKI activity bar panel for sessions and approvals\n"
        icon_svg = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 64 64\"><path fill=\"#1b4332\" d=\"M8 8h48v48H8z\"/><path fill=\"#f1faee\" d=\"M18 18h28l-14 28z\"/></svg>\n"
        written: Dict[str, str] = {}
        for name, payload in {
            "package.json": json.dumps(package_json, indent=2) + "\n",
            "extension.js": extension_js,
            "README.md": readme,
            "media/viki.svg": icon_svg,
        }.items():
            path = self.extension_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
            written[name] = str(path)
        return written
