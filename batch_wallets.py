#!/usr/bin/env python3
"""
Batch runner for wallet_tool.py (v3.2)
- verify: поддержка compare_file ИЛИ compare_from_latest_gen (автосбор эталона)
- Параллельность: --executor {thread,process}, --max-workers N
- Таймаут джобы: --job-timeout SEC
- Ротация логов: --max-log-bytes, --max-log-age-days, --keep-last-logs
- Раскраска консоли без зависимостей (--color {auto,always,never})
- Сводки: summary/*.csv|jsonl, manifest.json
"""
import argparse, json, os, re, subprocess, sys, time, csv, math
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
VERIFY_LINE = re.compile(
    r"^(receive|change)\[(\d+)\]\s*->\s*(\S+)\s*\((bitcoin|testnet|regtest)/(legacy|p2sh-segwit|segwit)\)\s*$"
)

# ---------- utils ----------
def ts(): return datetime.now().astimezone().isoformat(timespec="seconds")
def ensure_dir(p: Path): p.mkdir(parents=True, exist_ok=True); return p

def parse_size(s: str) -> int:
    s = str(s).strip().lower()
    if s in ("", "0", "0b"): return 0
    m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([kmg]?b?)?\s*$", s)
    if not m: raise ValueError(f"bad size: {s}")
    num = float(m.group(1)); unit = (m.group(2) or "").strip().lower()
    mul = 1
    if unit.startswith("k"): mul = 1024
    elif unit.startswith("m"): mul = 1024**2
    elif unit.startswith("g"): mul = 1024**3
    return int(num * mul)

def human_bytes(n: int) -> str:
    if n <= 0: return "0B"
    units = ["B","KB","MB","GB","TB"]
    i = min(int(math.log(n,1024)), len(units)-1)
    val = n / (1024**i)
    return f"{val:.1f}{units[i]}"

def supports_color(mode: str="auto") -> bool:
    if mode == "always": return True
    if mode == "never": return False
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

def colorizer(enabled: bool):
    def c(s, name=None):
        if not enabled or not name: return s
        names = {
            "green":"\033[32m","red":"\033[31m","yellow":"\033[33m",
            "cyan":"\033[36m","bold":"\033[1m","reset":"\033[0m"
        }
        return f"{names.get(name,'')}{s}{names['reset']}"
    return c

# ---------- logging ----------
def enforce_log_budget(logs_dir: Path, max_bytes: int, max_age_days: int, keep_last: int):
    logs_dir = ensure_dir(logs_dir)
    files = sorted(logs_dir.glob("job-*.log"), key=lambda p: p.stat().st_mtime)
    removed = []

    # По возрасту
    if max_age_days and max_age_days > 0:
        cutoff = time.time() - max_age_days * 86400
        for p in list(files):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink(missing_ok=True); removed.append(p); files.remove(p)
            except FileNotFoundError:
                pass

    # По суммарному объёму (сохраняем минимум keep_last самых свежих)
    if max_bytes and max_bytes > 0:
        def total():
            s = 0
            for p in files:
                try: s += p.stat().st_size
                except FileNotFoundError: pass
            return s
        while len(files) > keep_last and total() > max_bytes:
            p = files.pop(0)
            try: p.unlink(missing_ok=True); removed.append(p)
            except FileNotFoundError: pass

    return removed

# ---------- io helpers ----------
def append_jsonl(path: Path, rows):
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def write_csv(path: Path, rows):
    ensure_dir(path.parent)
    if not rows: return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

def load_jsonl(path: Path):
    rows=[]
    if not path or not path.exists(): return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if line:
                try: rows.append(json.loads(line))
                except Exception: pass
    return rows

# ---------- GEN artifacts ----------
def latest_jsonl_in(out_dir: Path, wallet: str, network: str, witness: str):
    patt = f"addresses-*-{wallet}-{network}-{witness}.jsonl"
    files = sorted(Path(out_dir).glob(patt), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def latest_jsonl_any(root: Path, wallet: str, network: str, witness: str):
    patt = f"addresses-*-{wallet}-{network}-{witness}.jsonl"
    files = sorted(root.rglob(patt), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def build_compare_from_latest_gen(exports_root: Path, wallet: str, network: str, witness: str,
                                  branch: str, start: int, count: int) -> Path|None:
    jl = latest_jsonl_any(exports_root, wallet, network, witness)
    if not jl: return None
    rows = load_jsonl(jl)
    end = start + count
    addrs = []
    for r in rows:
        try:
            if r.get("branch")==branch and start <= int(r.get("index",-1)) < end:
                a = r.get("address")
                if a: addrs.append(a)
        except Exception:
            pass
    # даже если нашли меньше, запишем что есть
    exp_dir = exports_root / "expected" / f"{wallet}_{network}_{witness}" / branch
    ensure_dir(exp_dir)
    exp_path = exp_dir / f"{wallet}_{network}_{witness}_{branch}_{start}_{count}.txt"
    exp_path.write_text("\n".join(addrs) + ("\n" if addrs else ""), encoding="utf-8")
    return exp_path if addrs else exp_path  # возвращаем путь в любом случае

# ---------- runner ----------
def run_and_capture(cmd, cwd: Path, log_path: Path, timeout_sec: int|None):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    timed_out = False
    lines = []
    with log_path.open("w", encoding="utf-8") as lf:
        lf.write(f"# CMD @ {ts()}: {' '.join(cmd)}\n")
        proc = subprocess.Popen(
            cmd, cwd=str(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        try:
            while True:
                if timeout_sec and (time.time() - start) > timeout_sec:
                    timed_out = True
                    proc.terminate()
                    try: proc.wait(timeout=5)
                    except subprocess.TimeoutExpired: proc.kill()
                    break
                line = proc.stdout.readline()
                if not line and proc.poll() is not None: break
                if line:
                    lf.write(line); lines.append(line.rstrip("\n"))
            rc = proc.poll()
        finally:
            lf.write(f"\n# EXIT @ {ts()}: {rc}{' (TIMEOUT)' if timed_out else ''}\n")
    return rc, lines, timed_out

# ---------- build commands ----------
def build_gen_cmd(py, tool, job, exports_root: Path):
    wallet  = job["wallet"]
    network = job.get("network","testnet")
    witness = job.get("witness","segwit")
    branch  = job.get("branch","receive")
    start   = int(job.get("start",0))
    count   = int(job.get("count",5))
    account = int(job.get("account",0))
    precr   = int(job.get("precreate",0))
    fmt     = job.get("format","csv,jsonl")
    xpub_file = job.get("xpub_file","")
    out_dir = Path(job.get("out_dir", exports_root / f"{wallet}_{network}_{witness}"))
    ensure_dir(out_dir)

    cmd = [py, tool, "gen",
           "--wallet", wallet,
           "--network", network,
           "--witness", witness,
           "--branch", branch,
           "--start", str(start),
           "--count", str(count),
           "--account", str(account),
           "--out-dir", str(out_dir),
           "--format", fmt]
    if precr>0: cmd += ["--precreate", str(precr)]
    if xpub_file: cmd += ["--xpub-file", xpub_file]
    return cmd, out_dir, wallet, network, witness

def build_verify_cmd(py, tool, job):
    xpub = job.get("xpub","").strip()
    xpub_file = job.get("xpub_file","").strip()
    if not xpub and xpub_file and Path(xpub_file).exists():
        xpub = Path(xpub_file).read_text(encoding="utf-8").strip()
    if not xpub:
        raise ValueError("verify: required xpub or xpub_file")

    cmd = [py, tool, "verify",
           "--xpub", xpub,
           "--network", job.get("network","testnet"),
           "--witness", job.get("witness","segwit"),
           "--branch", job.get("branch","receive"),
           "--start", str(int(job.get("start",0))),
           "--count", str(int(job.get("count",5)))]
    if job.get("compare_file",""):
        cmd += ["--compare-file", job["compare_file"]]
    return cmd

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description="Batch runner for wallet_tool.py (v3.2)")
    ap.add_argument("--config", required=True, help="JSON с job'ами: gen/verify")
    ap.add_argument("--exports-dir", default=str(HERE / "mass_exports"), help="Корень артефактов")
    ap.add_argument("--wallet-tool", default=str(HERE / "wallet_tool.py"))
    ap.add_argument("--max-workers", type=int, default=4, help="Параллельность")
    ap.add_argument("--executor", choices=["thread","process"], default="thread", help="Тип пула")
    ap.add_argument("--job-timeout", type=int, default=0, help="Таймаут каждой джобы в секундах (0=без)")
    # Ротация логов:
    ap.add_argument("--max-log-bytes", default="200MB", help="Лимит суммарного размера логов (0=без)")
    ap.add_argument("--max-log-age-days", type=int, default=14, help="Удалять логи старше N дней (0=не удалять)")
    ap.add_argument("--keep-last-logs", type=int, default=30, help="Минимум последних файлов логов, которые нельзя удалять")
    # Цвета:
    ap.add_argument("--color", choices=["auto","always","never"], default="auto")
    args = ap.parse_args()

    COLOR = colorizer(supports_color(args.color))
    exports_root = ensure_dir(Path(args.exports_dir))
    logs_dir = ensure_dir(exports_root / "logs")
    summary_dir = ensure_dir(exports_root / "summary")

    removed = enforce_log_budget(
        logs_dir,
        parse_size(args.max_log_bytes),
        args.max_log_age_days,
        args.keep_last_logs
    )
    if removed:
        print(COLOR(f"[logs] удалено старых файлов: {len(removed)}", "yellow"))

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    jobs = cfg.get("jobs", [])
    if not jobs:
        print(COLOR("Пустой jobs[]", "red"), file=sys.stderr); sys.exit(2)

    py = sys.executable
    tool = str(Path(args.wallet_tool).resolve())

    futures = []
    results_meta = []
    summary_gen, summary_verify, failures = [], [], []

    Executor = ThreadPoolExecutor if args.executor == "thread" else ProcessPoolExecutor
    with Executor(max_workers=args.max_workers) as ex:
        for idx,job in enumerate(jobs, start=1):
            jtype = (job.get("type") or "").lower().strip()
            jid = f"{idx:03d}-{jtype if jtype else 'unknown'}"
            log_path = logs_dir / f"job-{jid}-{int(time.time())}.log"

            if jtype == "gen":
                try:
                    cmd, out_dir, wallet, network, witness = build_gen_cmd(py, tool, job, exports_root)
                except Exception as e:
                    failures.append({"job": jid, "type": "gen", "error": str(e)}); continue
                futures.append(ex.submit(run_and_capture, cmd, HERE, log_path, args.job_timeout))
                results_meta.append(("gen", jid, log_path, out_dir, wallet, network, witness))

            elif jtype == "verify":
                # авто-эталон, если попросили:
                if not job.get("compare_file") and job.get("compare_from_latest_gen"):
                    wallet = job.get("wallet")
                    if not wallet:
                        failures.append({"job": jid, "type":"verify", "error":"compare_from_latest_gen требует поле 'wallet'"}); 
                    else:
                        branch = job.get("branch","receive")
                        start  = int(job.get("start",0))
                        count  = int(job.get("count",5))
                        exp = build_compare_from_latest_gen(
                            exports_root,
                            wallet=wallet,
                            network=job.get("network","testnet"),
                            witness=job.get("witness","segwit"),
                            branch=branch, start=start, count=count
                        )
                        job["compare_file"] = str(exp) if exp else ""

                try:
                    cmd = build_verify_cmd(py, tool, job)
                except Exception as e:
                    failures.append({"job": jid, "type": "verify", "error": str(e)}); continue
                futures.append(ex.submit(run_and_capture, cmd, HERE, log_path, args.job_timeout))
                results_meta.append(("verify", jid, log_path, None, None, None, None))

            else:
                failures.append({"job": jid, "type": "unknown", "raw": job})

        for fut, meta in zip(as_completed(futures), results_meta):
            kind, jid, log_path, out_dir, wallet, network, witness = meta
            try:
                rc, out_lines, timed_out = fut.result()
            except Exception as e:
                failures.append({"job": jid, "type": kind, "error": f"exec failed: {e}", "log": str(log_path)})
                continue

            if kind == "gen":
                if rc != 0 or timed_out:
                    failures.append({"job": jid, "type": "gen", "rc": rc, "timeout": timed_out, "log": str(log_path)})
                    print(COLOR(f"[gen:{jid}] FAIL rc={rc}{' TIMEOUT' if timed_out else ''}", "red"))
                else:
                    print(COLOR(f"[gen:{jid}] OK", "green"))
                jl = latest_jsonl_in(out_dir, wallet, network, witness)
                if jl:
                    rows = load_jsonl(jl)
                    for r in rows:
                        r["_job"] = jid; r["_jsonl_path"] = str(jl)
                    summary_gen.extend(rows)
                else:
                    failures.append({"job": jid, "type": "gen", "error": "jsonl not found", "log": str(log_path)})

            elif kind == "verify":
                if rc != 0 or timed_out:
                    failures.append({"job": jid, "type": "verify", "rc": rc, "timeout": timed_out, "log": str(log_path)})
                    print(COLOR(f"[verify:{jid}] FAIL rc={rc}{' TIMEOUT' if timed_out else ''}", "red"))
                else:
                    print(COLOR(f"[verify:{jid}] OK", "green"))
                for line in out_lines:
                    m = VERIFY_LINE.match(line.strip())
                    if m:
                        br, idx_s, addr, net, wit = m.groups()
                        summary_verify.append({
                            "timestamp": ts(),
                            "branch": br,
                            "index": int(idx_s),
                            "address": addr,
                            "network": net,
                            "witness": wit,
                            "_job": jid,
                            "_log": str(log_path),
                        })

    # --- сводки ---
    if summary_gen:
        write_csv(summary_dir / "gen_addresses.csv", summary_gen)
        append_jsonl(summary_dir / "gen_addresses.jsonl", summary_gen)
    if summary_verify:
        write_csv(summary_dir / "verify_addresses.csv", summary_verify)
        append_jsonl(summary_dir / "verify_addresses.jsonl", summary_verify)
    (summary_dir / "manifest.json").write_text(json.dumps({
        "generated_rows": len(summary_gen),
        "verified_rows": len(summary_verify),
        "failures": failures,
        "created_at": ts()
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    total_log_bytes = sum((p.stat().st_size for p in (exports_root/"logs").glob("job-*.log")), start=0)
    print()
    print(colorizer(True)("== Итоги ==", "bold"))
    print(colorizer(True)(f"GEN rows:     {len(summary_gen)}  -> {summary_dir/'gen_addresses.csv'}", "cyan"))
    print(colorizer(True)(f"VERIFY rows:  {len(summary_verify)} -> {summary_dir/'verify_addresses.csv'}", "cyan"))
    print(colorizer(True)(f"FAILURES:     {len(failures)}       (см. {summary_dir/'manifest.json'})", "yellow" if failures else "green"))
    print(colorizer(True)(f"Логи:         {exports_root/'logs'}  ({human_bytes(total_log_bytes)})", "cyan"))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
