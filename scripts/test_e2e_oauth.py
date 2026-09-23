import json
import urllib.request
import urllib.parse
import urllib.error
import hashlib
import base64
import os
import ssl

def run_test():
    base = "https://funk-believes-precision-guaranteed.trycloudflare.com"
    print(f"Testing MCP OAuth against: {base}")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # 1. Register Client (DCR)
    reg_url = f"{base}/register"
    reg_data = {
        "client_name": "Claude Test E2E",
        "redirect_uris": ["https://claude.ai/api/auth/callback/mcp"]
    }
    req = urllib.request.Request(
        reg_url,
        data=json.dumps(reg_data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, context=ctx) as resp:
        reg_resp = json.loads(resp.read().decode("utf-8"))
    
    client_id = reg_resp["client_id"]
    client_secret = reg_resp.get("client_secret", "")
    print(f"1. DCR success: client_id={client_id}, scope={reg_resp.get('scope')}")

    # 2. PKCE setup
    verifier = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8").rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("utf-8").rstrip("=")

    # 3. Authorize request
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": "https://claude.ai/api/auth/callback/mcp",
        "scope": "cving:market:read",
        "state": "state-test-123",
        "code_challenge": challenge,
        "code_challenge_method": "S256"
    }
    auth_url = f"{base}/authorize?{urllib.parse.urlencode(params)}"

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), NoRedirect)
    consent_url = None
    try:
        opener.open(auth_url)
    except urllib.error.HTTPError as e:
        if e.code in (302, 303, 307):
            loc = e.headers.get("Location")
            consent_url = urllib.parse.urljoin(base, loc)
            print(f"2. Authorize 302 -> Consent URL: {consent_url}")
        else:
            raise RuntimeError(f"Authorize failed: {e.code} {e.read()}")

    if "error=" in consent_url:
        raise RuntimeError(f"Authorize returned error in redirect: {consent_url}")

    # 4. Consent page GET
    with urllib.request.urlopen(consent_url, context=ctx) as resp:
        consent_html = resp.read().decode("utf-8")
        assert "Authorize Client" in consent_html or "Password" in consent_html, "Consent page HTML invalid"
        print("3. Consent page rendered successfully")

    # 5. Consent POST (approval)
    req_id = urllib.parse.parse_qs(urllib.parse.urlparse(consent_url).query)["request_id"][0]
    post_data = urllib.parse.urlencode({
        "request_id": req_id,
        "password": "CvingTrade25X-OAuth-Owner-Secret-2026!",
        "action": "approve"
    }).encode("utf-8")

    code = None
    try:
        consent_req = urllib.request.Request(
            f"{base}/oauth/consent",
            data=post_data,
            headers={"Origin": base, "Content-Type": "application/x-www-form-urlencoded"}
        )
        opener.open(consent_req)
    except urllib.error.HTTPError as e:
        if e.code in (302, 303):
            cb_url = e.headers.get("Location")
            print(f"4. Consent approved -> Callback URL: {cb_url}")
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(cb_url).query)
            code = qs["code"][0]
            assert qs["state"][0] == "state-test-123"
        else:
            raise RuntimeError(f"Consent POST failed: {e.code} {e.read()}")

    print(f"5. Acquired authorization code: {code[:10]}...")

    # 6. Exchange code for token
    token_url = f"{base}/token"
    token_post = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": "https://claude.ai/api/auth/callback/mcp",
        "code_verifier": verifier
    }).encode("utf-8")

    token_req = urllib.request.Request(token_url, data=token_post, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(token_req, context=ctx) as resp:
        token_data = json.loads(resp.read().decode("utf-8"))
    
    access_token = token_data["access_token"]
    print(f"6. Acquired access token: {access_token[:15]}... expires_in={token_data.get('expires_in')}")

    # 7. Use token to call MCP endpoint
    mcp_url = f"{base}/mcp"
    mcp_post = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }).encode("utf-8")
    mcp_req = urllib.request.Request(
        mcp_url,
        data=mcp_post,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {access_token}"
        }
    )
    with urllib.request.urlopen(mcp_req, context=ctx) as resp:
        mcp_resp = json.loads(resp.read().decode("utf-8"))
        tools = mcp_resp.get("result", {}).get("tools", [])
        print(f"7. MCP tools/list via issued OAuth token returned {len(tools)} tools!")
        tool_names = [t["name"] for t in tools]
        print(f"   Tools: {tool_names[:5]}... (total {len(tools)})")

    print("\n=======================================================")
    print("SUCCESS: ALL 7 STEPS OF OAUTH 2.1 SUCCEEDED OVER CLOUDFLARE TUNNEL!")
    print("=======================================================")

if __name__ == "__main__":
    run_test()
