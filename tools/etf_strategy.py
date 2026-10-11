"""가상운용 ETF 전략의 거래를 규칙대로 적는다. 매일 갱신(시세 받기) 뒤에 돌린다.

data/strategies.yaml에서 auto가 적힌 전략만 다룬다. 새 거래는 data/trades/전략id.csv 끝에 붙이고,
어디까지 판정했는지는 data/trades/전략id.state.json에 적는다. 여러 번 돌려도 같은 거래를 두 번 적지 않는다.
기준금리는 data/rates/bok_base_rate.csv(tools/update_base_rate.py가 받는다)를 읽는다.

실행:  python tools/etf_strategy.py            새 거래가 있으면 적는다
       python tools/etf_strategy.py --dry-run  적지 않고 보여 주기만 한다
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib import etf_rule as R  # noqa: E402
from lib import portfolio as PF  # noqa: E402


def read_prices(name):
    with open(ROOT / "data" / "prices" / f"{name}.csv", encoding="utf-8") as f:
        return {date.fromisoformat(r["date"]): float(r["close"]) for r in csv.DictReader(f)}


def read_rates():
    with open(ROOT / "data" / "rates" / "bok_base_rate.csv", encoding="utf-8") as f:
        return sorted((date.fromisoformat(r["date"]), float(r["rate"])) for r in csv.DictReader(f))


def read_trades(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [PF.Trade(date.fromisoformat(r["date"]), r["asset"], r["side"], float(r["qty"]), float(r["price"]), r.get("note", "")) for r in csv.DictReader(f)]


def main(argv=None):
    dry = "--dry-run" in (argv or sys.argv[1:])
    site = yaml.safe_load((ROOT / "data" / "site.yaml").read_text(encoding="utf-8"))
    strategies = yaml.safe_load((ROOT / "data" / "strategies.yaml").read_text(encoding="utf-8")) or []
    rates = read_rates()
    n_new = 0
    for s in strategies:
        if not s.get("auto") or s.get("status") != "운용 중":
            continue
        bench = read_prices(site["benchmarks"][s["benchmark"]])
        prices = {a: read_prices(a) for a in s["auto"]["weights"]}
        tpath = ROOT / "data" / "trades" / f"{s['id']}.csv"
        spath = ROOT / "data" / "trades" / f"{s['id']}.state.json"
        state = json.loads(spath.read_text(encoding="utf-8")) if spath.exists() else {"last_decision": None, "rising": None}
        new, state2 = R.new_trades(s, prices, sorted(bench), rates, read_trades(tpath), state)
        for t in new:
            print(f"{s['id']}: {t.date} {t.asset} {t.side} {t.qty:g}주 @ {t.price:,.0f}  ({t.note})")
        if state2 != state:
            print(f"{s['id']}: 판정 {state2['last_decision']}까지, 금리 조건 {'켜짐' if state2['rising'] else '꺼짐'}")
        n_new += len(new)
        if dry:
            continue
        if new:
            fresh = not tpath.exists() or tpath.stat().st_size == 0
            with open(tpath, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if fresh:
                    w.writerow(["date", "asset", "side", "qty", "price", "note"])
                for t in new:
                    w.writerow([t.date.isoformat(), t.asset, t.side, f"{t.qty:g}", f"{t.price:g}", t.note])
        if state2 != state:
            spath.write_text(json.dumps(state2, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"새 거래 {n_new}건" + (" (적지 않음)" if dry else ""))


if __name__ == "__main__":
    main()
