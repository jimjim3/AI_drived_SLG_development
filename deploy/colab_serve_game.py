# Paste this into ONE Colab cell (CPU runtime is enough) to put the game on a temporary public URL.
# Before running: Colab sidebar -> Secrets (key icon), add and enable
#   GITHUB_TOKEN   (only needed if the repo is private; fine-grained, read-only "Contents")
#   NVIDIA_API_KEY (optional, enables the "nim" opponent)
#   SLG_QWEN_URL   (optional, the https://....trycloudflare.com/v1 URL of your Qwen server)
import os, re, secrets, subprocess, sys, time, urllib.request

REPO = "jimjim3/AI_drived_SLG_development"
BRANCH = "claude/ai-hierarchical-slg-game-fl3ojj"

try:
    from google.colab import userdata
    def secret(name):
        try:
            return userdata.get(name)
        except Exception:
            return None
except ImportError:
    secret = lambda name: os.environ.get(name)

if not os.path.isdir("slg-game"):
    gh = secret("GITHUB_TOKEN")
    url = f"https://{gh + '@' if gh else ''}github.com/{REPO}.git"
    subprocess.run(["git", "clone", "-q", "--depth", "1", "-b", BRANCH, url, "slg-game"], check=True)
else:
    subprocess.run(["git", "-C", "slg-game", "pull", "-q"], check=False)

if not os.path.exists("/usr/local/bin/cloudflared"):
    urllib.request.urlretrieve(
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
        "/usr/local/bin/cloudflared")
    os.chmod("/usr/local/bin/cloudflared", 0o755)

env = dict(os.environ, PYTHONPATH="slg-game/src", SLG_ACCESS_TOKEN=secrets.token_urlsafe(18))
for name in ("NVIDIA_API_KEY", "SLG_QWEN_URL"):
    value = secret(name)
    if value:
        env[name] = value

server = subprocess.Popen([sys.executable, "-m", "slg.web.server", "8080"], env=env)
time.sleep(2)
tunnel = subprocess.Popen(["cloudflared", "tunnel", "--url", "http://127.0.0.1:8080"],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
public = None
for line in tunnel.stdout:
    m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
    if m:
        public = m.group(0)
        break

print("=" * 70)
if public:
    print("Open this link (the access token is part of it; do not share it):")
    print(f"  {public}/?token={env['SLG_ACCESS_TOKEN']}")
    print("Opponents offered in the setup screen:",
          "rule, demo" + (", nim" if "NVIDIA_API_KEY" in env else "") + (", qwen" if "SLG_QWEN_URL" in env else ""))
else:
    print("Could not get a tunnel URL; run this cell again.")
print("Keep this cell running. Stop it (and the runtime) when you are done to save compute units.")
print("=" * 70)
try:
    while True:
        time.sleep(60)
except KeyboardInterrupt:
    tunnel.terminate(); server.terminate()
