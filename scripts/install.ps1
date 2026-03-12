param(
  [switch]$Run,
  [switch]$Dev,
  [switch]$ForceEnv,
  [string]$Host = "127.0.0.1",
  [string]$Port = "8787"
)
$cmd = @("scripts/install.py", "--path", ".", "--host", $Host, "--port", $Port)
if ($Run) { $cmd += "--run" }
if ($Dev) { $cmd += "--dev" }
if ($ForceEnv) { $cmd += "--force-env" }
python @cmd
