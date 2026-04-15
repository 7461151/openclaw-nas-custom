#!/usr/bin/env python3
from pathlib import Path
import os
import re
import sys

MARKER = "OPENCLAW_DELIVERY_MIRROR_UI_PATCH"
PATCH_VERSION = "2026-04-15.1"
DEFAULT_ASSETS_DIR = Path("/app/dist/control-ui/assets")

OLD_SNIPPET = (
    "function gT(e,t){let n=0,r=0,i=0,a=0,o=0,s=null,c=!1;for(let{message:t}of "
    "e.messages){let e=t;if(e.role!==`assistant`)continue;let l=e.usage;l&&(c=!0,"
    "n+=l.input??l.inputTokens??0,r+=l.output??l.outputTokens??0,i+=l.cacheRead??"
    "l.cache_read_input_tokens??0,a+=l.cacheWrite??l.cache_creation_input_tokens??0);"
    "let u=e.cost;u?.total&&(o+=u.total),typeof e.model==`string`&&e.model!=="
    "`gateway-injected`&&(s=e.model)}if(!c&&!s)return null;let l=t&&n>0?"
    "Math.min(Math.round(n/t*100),100):null;return{input:n,output:r,cacheRead:i,"
    "cacheWrite:a,cost:o,model:s,contextPercent:l}}"
)

NEW_SNIPPET = (
    f"const {MARKER}=`{PATCH_VERSION}`;"
    "function pT(e){if(!e||typeof e!=`object`)return!1;let t=typeof e.provider==`string`?"
    "O(e.provider):``,n=typeof e.model==`string`?O(e.model):``;return n===`delivery-mirror`&&"
    "(t===``||t===`openclaw`)}"
    "function mT(e){return typeof e.model==`string`&&e.model!==`gateway-injected`&&!pT(e)}"
    "function gT(e,t){let n=0,r=0,i=0,a=0,o=0,s=null,c=!1;for(let{message:t}of e.messages)"
    "{let e=t;if(e.role!==`assistant`)continue;let l=e.usage;l&&(c=!0,n+=l.input??l.inputTokens??0,"
    "r+=l.output??l.outputTokens??0,i+=l.cacheRead??l.cache_read_input_tokens??0,"
    "a+=l.cacheWrite??l.cache_creation_input_tokens??0);let u=e.cost;u?.total&&(o+=u.total),"
    "mT(e)&&(s=e.model)}if(!c&&!s)return null;let l=t&&n>0?Math.min(Math.round(n/t*100),100):null;"
    "return{input:n,output:r,cacheRead:i,cacheWrite:a,cost:o,model:s,contextPercent:l}}"
)


def log(message: str) -> None:
    print(f"[control-ui-delivery-model] {message}")


def resolve_assets_dir() -> Path:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return Path(sys.argv[1].strip())
    override = os.environ.get("OPENCLAW_CONTROL_UI_ASSETS_DIR", "").strip()
    if override:
        return Path(override)
    return DEFAULT_ASSETS_DIR


def find_target_file(assets_dir: Path) -> Path:
    patched_candidates = []
    fresh_candidates = []
    for path in sorted(assets_dir.glob("index-*.js")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if MARKER in text and "function gT(e,t)" in text:
            patched_candidates.append(path)
            continue
        if OLD_SNIPPET in text:
            fresh_candidates.append(path)
    if patched_candidates:
        return patched_candidates[0]
    if fresh_candidates:
        return fresh_candidates[0]
    raise RuntimeError("control-ui index asset not found")


def patch_text(text: str) -> str:
    if MARKER in text:
        pattern = re.compile(
            rf"const {MARKER}=`.*?`;function pT\(e\)\{{.*?function gT\(e,t\)\{{.*?return\{{input:n,output:r,cacheRead:i,cacheWrite:a,cost:o,model:s,contextPercent:l\}}\}}",
            re.S,
        )
        if not pattern.search(text):
            raise RuntimeError("existing control-ui patch marker found but helper block shape changed")
        return pattern.sub(NEW_SNIPPET, text, count=1)
    if OLD_SNIPPET not in text:
        raise RuntimeError("target gT snippet not found")
    return text.replace(OLD_SNIPPET, NEW_SNIPPET, 1)


def main() -> int:
    assets_dir = resolve_assets_dir()
    target = find_target_file(assets_dir)
    original = target.read_text(encoding="utf-8")
    patched = patch_text(original)
    if patched == original:
        log(f"patch already present for {target.name} ({PATCH_VERSION})")
        return 0
    target.write_text(patched, encoding="utf-8")
    log(f"patched {target.name} -> {PATCH_VERSION}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"failed: {exc}")
        raise
