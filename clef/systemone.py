#!/usr/bin/env python3
"""Experiments with the llama.cpp /v1/systemone API (decision models, PR #29818).

usage: python systemone.py <experiment> [--url http://127.0.0.1:8081] [--url2 ...] [--raw | -q]

every call prints what was sent (state, questions, criteria) and what came back (answers, probabilities,
latency, tokens); --raw prints the exact request and response JSON instead, -q prints only the summaries

experiments:
  basic       the README request, pretty-printed
  order       permute the options of a choice question: does the answer move?
  criteria    noul with vs without true/false descriptions
  score       expected score vs most likely level, and how confidence behaves
  paraphrase  same question, reworded: how stable is the probability?
  sweep       vary the state gradually and watch a noul probability move
  many        N questions in one request vs N requests: latency + input_tokens
  compare     same request on two servers (--url, --url2), side by side
"""

import argparse
import itertools
import json
import os
import statistics
import time
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8081"
SHOW = "summary"  # summary | raw | none, set from the command line
N_CALLS = 0

TICKET = "Hi, I was charged twice for my order #4471 and I want a refund. This is the third time I'm writing!"


def _short(v, n=110):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[: n - 1] + "…"


def show_request(n, url, body):
    print(f"\n┌─ #{n} SENT  POST {url}/v1/systemone")
    print(f"│ state: {_short(body['state'], 200)}")
    if body.get("images"):
        print(f"│ images: {len(body['images'])} data URL(s)")
    for qid, q in body["questions"].items():
        print(f"│ {qid} [{q['type']}]: {_short(q['instructions'])}")
        crit = q.get("criteria")
        items = crit.items() if isinstance(crit, dict) else enumerate(crit) if isinstance(crit, list) else []
        for k, v in items:
            print(f"│     {k}: {'(no description)' if v is None else _short(v, 80)}")


def show_response(out):
    model = os.path.basename(out.get("model", "?"))
    print(f"├─ RECEIVED  {out['_ms']:.0f} ms  input_tokens={out['usage']['input_tokens']}  model={model}")
    for qid, a in out["answers"].items():
        if a["type"] == "noul":
            print(f"│ {qid} → P(true) = {a['noul']:.4f}")
            continue
        probs = sorted(a["probabilities"].items(), key=lambda kv: -kv[1])
        dist = "  ".join(f"{k}={p:.3f}" for k, p in probs)
        if a["type"] == "choice":
            print(f"│ {qid} → {a['choice']}  (confidence {a['confidence']:.2f})")
        else:
            mode = probs[0][0]
            print(f"│ {qid} → score {a['score']:.2f}, most likely {mode} = {a['legend'][mode]!r}"
                  f"  (confidence {a['confidence']:.2f})")
        print(f"│     {dist}")
    print("└─")


def summary(title):
    # separates the experiment's result from the request/response blocks above it
    if SHOW != "none":
        print(f"\n═══ {title} " + "═" * max(3, 70 - len(title)))


def ask(state, questions, url=None, images=None):
    global N_CALLS
    N_CALLS += 1
    url = url or URL
    body = {"state": state, "questions": questions}
    if images:
        body["images"] = images
    if SHOW == "summary":
        show_request(N_CALLS, url, body)
    elif SHOW == "raw":
        print(f"\n>>> #{N_CALLS} POST {url}/v1/systemone\n{json.dumps(body, indent=2, ensure_ascii=False)}")
    req = urllib.request.Request(
        url + "/v1/systemone",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code}: {e.read().decode()}")
    ms = (time.perf_counter() - t0) * 1000
    if SHOW == "raw":
        print(f"<<< #{N_CALLS} {ms:.0f} ms\n{json.dumps(out, indent=2, ensure_ascii=False)}")
    out["_ms"] = ms
    if SHOW == "summary":
        show_response(out)
    return out


def choice(instructions, options):
    return {"type": "choice", "instructions": instructions, "criteria": options}


def noul(instructions, criteria=None):
    q = {"type": "noul", "instructions": instructions}
    if criteria:
        q["criteria"] = criteria
    return q


def score(instructions, levels):
    return {"type": "score", "instructions": instructions, "criteria": levels}


# --- experiments ---------------------------------------------------------------


def exp_basic(a):
    out = ask(
        {"message": TICKET, "plan": "pro", "order": {"id": 4471, "items": ["phone case", "charger"]}},
        {
            "intent": choice(
                "What does the customer want?",
                {"refund": "wants money back", "cancel": "wants to cancel an order",
                 "track": "wants to know where an order is", "other": "anything else"},
            ),
            "urgent": noul("Does this need a human within the hour?"),
            "frustration": score("How frustrated is the customer?", ["calm", "mildly annoyed", "annoyed", "angry"]),
        },
        a.url,
    )
    if SHOW == "none":
        print(json.dumps({k: v for k, v in out.items() if k != "_ms"}, indent=2))


def exp_order(a):
    # Position bias: a model reading label-token logits (lev/openjev) may favour "A".
    # lev cancels this by averaging 2 variants (forward + reversed); laya scores each option at its own marker.
    opts = {"billing": "payments, charges, invoices", "shipping": "delivery, tracking",
            "technical": "app or device problems", "returns": "sending items back"}
    keys = list(opts)
    rows = []
    for perm in itertools.permutations(keys):
        out = ask(TICKET, {"q": choice("Which team should handle this?", {k: opts[k] for k in perm})}, a.url)
        p = out["answers"]["q"]["probabilities"]
        rows.append((perm, p))
    summary("order: P(option) for each of the 24 orders")
    print(f"{'order':45} " + " ".join(f"{k:>9}" for k in keys))
    for perm, p in rows:
        print(f"{','.join(k[:4] for k in perm):45} " + " ".join(f"{p[k]:9.4f}" for k in keys))
    for k in keys:
        vals = [p[k] for _, p in rows]
        print(f"{k:10} mean={statistics.mean(vals):.4f}  spread={max(vals) - min(vals):.4f}")


def exp_criteria(a):
    qs = {
        "bare": noul("Is a refund requested?"),
        "described": noul("Is a refund requested?",
                          {"true": "the customer asks for money back", "false": "no money back is asked"}),
        "inverted_desc": noul("Is a refund requested?",
                              {"true": "no money back is asked", "false": "the customer asks for money back"}),
    }
    states = [TICKET, "Where is my order #4471? It has not arrived yet."]
    outs = [ask(state, qs, a.url) for state in states]
    summary("criteria: P(true) with bare / described / swapped descriptions")
    for state, out in zip(states, outs):
        print(state[:60])
        for k, v in out["answers"].items():
            print(f"  {k:14} P(true)={v['noul']:.4f}")


def exp_score(a):
    levels = ["calm", "mildly annoyed", "annoyed", "angry", "furious"]
    msgs = [
        "Thanks, the package arrived, all good.",
        "My order is a day late, could you check?",
        "Still no reply. This is getting ridiculous.",
        TICKET,
        "THIS IS A SCAM. I'M REPORTING YOU. GIVE ME MY MONEY NOW!!!",
    ]
    rs = [ask(msg, {"f": score("How frustrated is the customer?", levels)}, a.url)["answers"]["f"] for msg in msgs]
    summary("score: expected score vs most likely level (mode)")
    for msg, r in zip(msgs, rs):
        probs = [r["probabilities"][str(i)] for i in range(len(levels))]
        mode = max(range(len(probs)), key=probs.__getitem__)
        bar = " ".join(f"{p:.2f}" for p in probs)
        print(f"score={r['score']:.2f} mode={mode} conf={r['confidence']:.2f}  [{bar}]  {msg[:45]}")


def exp_paraphrase(a):
    variants = [
        "Is the customer asking for a refund?",
        "Does the customer want their money back?",
        "Refund requested?",
        "Would the customer be satisfied only if the charge is reversed?",
        "Is this a refund request? Answer true or false.",
    ]
    out = ask(TICKET, {f"v{i}": noul(v) for i, v in enumerate(variants)}, a.url)
    summary("paraphrase: P(true) for each wording")
    for i, v in enumerate(variants):
        print(f"{out['answers'][f'v{i}']['noul']:.4f}  {v}")


def exp_sweep(a):
    steps = [
        "The package arrived.",
        "The package arrived but the box was dented.",
        "The package arrived but the charger inside is cracked.",
        "The package arrived broken, I want a replacement.",
        "The package arrived broken, I want my money back.",
        "The package arrived broken and I was charged twice. Refund me now.",
    ]
    ps = [ask(s, {"r": noul("Is a refund requested?")}, a.url)["answers"]["r"]["noul"] for s in steps]
    summary("sweep: P(refund) as the state changes")
    for s, p in zip(steps, ps):
        print(f"{p:.4f} {'#' * int(p * 40):40}  {s}")


def exp_many(a):
    n = a.n
    qs = {f"q{i}": noul(f"Does the message mention topic number {i}: " + ["billing", "shipping", "refunds",
          "anger", "an order id", "a product", "repeat contact", "a deadline"][i % 8] + "?") for i in range(n)}
    state = {"message": TICKET, "history": [TICKET] * 6}  # a longer state makes prefix sharing matter
    ask(state, {"q0": qs["q0"]}, a.url)  # warm-up
    one = ask(state, qs, a.url)
    t0 = time.perf_counter()
    tok = 0
    for k, q in qs.items():
        tok += ask(state, {k: q}, a.url)["usage"]["input_tokens"]
    sep_ms = (time.perf_counter() - t0) * 1000
    summary(f"many: {n} questions in one request vs {n} requests")
    print(f"{n} questions, one request : {one['_ms']:8.1f} ms  input_tokens={one['usage']['input_tokens']}")
    print(f"{n} questions, {n} requests: {sep_ms:8.1f} ms  input_tokens={tok}")
    print("(input_tokens counts every question's full prompt; the speedup comes from evaluating the shared prefix once)")


def exp_compare(a):
    if not a.url2:
        raise SystemExit("compare needs --url2")
    qs = {
        "intent": choice("What does the customer want?",
                         {"refund": None, "cancel": None, "track": None, "other": None}),
        "refund": noul("Is a refund requested?"),
        "urgent": noul("Does this need a human within the hour?"),
        "frustration": score("How frustrated is the customer?", ["calm", "mildly annoyed", "annoyed", "angry"]),
    }
    r1, r2 = ask(TICKET, qs, a.url), ask(TICKET, qs, a.url2)
    summary("compare: same request on both servers")
    m1, m2 = (os.path.basename(r["model"])[:22] for r in (r1, r2))
    print(f"{'question':12} {m1:>24} {m2:>24}")

    def summ(x):
        return {"choice": lambda: f"{x['choice']} ({x['probabilities'][x['choice']]:.3f})",
                "noul": lambda: f"{x['noul']:.4f}",
                "score": lambda: f"{x['score']:.2f} c={x['confidence']:.2f}"}[x["type"]]()

    for k in qs:
        print(f"{k:12} {summ(r1['answers'][k]):>24} {summ(r2['answers'][k]):>24}")
    print(f"{'ms':12} {r1['_ms']:>24.1f} {r2['_ms']:>24.1f}")
    print(f"{'tokens':12} {r1['usage']['input_tokens']:>24} {r2['usage']['input_tokens']:>24}")


if __name__ == "__main__":
    exps = {k[4:]: v for k, v in globals().items() if k.startswith("exp_")}
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("experiment", choices=exps)
    p.add_argument("--url", default=URL)
    p.add_argument("--url2")
    p.add_argument("-n", type=int, default=16, help="questions for 'many'")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--raw", action="store_true", help="print the exact request and response JSON of every call")
    g.add_argument("-q", "--quiet", action="store_true", help="print only the experiment's summary")
    args = p.parse_args()
    SHOW = "raw" if args.raw else "none" if args.quiet else "summary"
    exps[args.experiment](args)
