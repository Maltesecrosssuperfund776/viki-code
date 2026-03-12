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
    terminal.sendText(`viki run "${prompt.replace(/"/g, '\"')}" --path .`);
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
