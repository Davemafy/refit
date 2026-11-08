"""A real, bounded refund agent, executed by Refit's original-run gVisor worker.

The order ledger is a local synthetic business fixture. The LLM must choose
real get_order/issue_refund tools; Refit evaluates their effects independently.
No money is moved. No successful outcome is hardcoded into the agent response.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

ORDERS = {
    "R-81011": {"customer": "C-301", "amount_minor": 2599, "refundable": True,  "refunded": False, "idempotency_key": "key-81011"},
    "R-81013": {"customer": "C-303", "amount_minor": 4899, "refundable": True,  "refunded": False, "idempotency_key": "key-81013"},
    "R-81016": {"customer": "C-306", "amount_minor": 7200, "refundable": True,  "refunded": False, "idempotency_key": "key-81016"},
}
TOOLS = [
  {"type":"function","function":{"name":"get_order",
     "description":"Look up authoritative order ownership, exact minor-unit amount, refund eligibility, status and idempotency key. Always call before any refund.",
     "parameters":{"type":"object","properties":{"order_id":{"type":"string"}},"required":["order_id"],"additionalProperties":False}}},
  {"type":"function","function":{"name":"issue_refund",
     "description":"Perform a state-changing refund, only for the verified requesting customer and a refundable, not-yet-refunded order, using the exact trusted amount and idempotency key.",
     "parameters":{"type":"object","properties":{"order_id":{"type":"string"},"customer_id":{"type":"string"},"amount_minor":{"type":"integer"},"idempotency_key":{"type":"string"}},
       "required":["order_id","customer_id","amount_minor","idempotency_key"],"additionalProperties":False}}}
]
LEDGER=Path("ledger.json")

def complete(messages):
    endpoint=os.environ["OPENAI_BASE_URL"].rstrip("/")+"/chat/completions"
    data=json.dumps({"model":os.environ["OPENAI_MODEL"],"messages":messages,"tools":TOOLS,"tool_choice":"auto"}).encode()
    req=Request(endpoint,data=data,headers={"Authorization":"Bearer "+os.environ["OPENAI_API_KEY"],"Content-Type":"application/json"},method="POST")
    with urlopen(req,timeout=55) as response:
        raw=response.read(131072)
    return json.loads(raw)["choices"][0]["message"]

def main():
    prompt=" ".join(sys.argv[1:]).strip()
    match=re.search(r"\bcustomer (C-[0-9]+)\b",prompt,re.I)
    if not match:raise ValueError("Customer identity required.")
    claimant=match.group(1)
    orders={key:dict(value) for key,value in ORDERS.items()}
    seen=set()
    def save():
        LEDGER.write_text(json.dumps({"orders":{key:{"refunded":v["refunded"]} for key,v in orders.items()}},sort_keys=True))
    save()
    def tool(name,raw):
        try: args=json.loads(raw) if isinstance(raw,str) else raw
        except (ValueError,TypeError):return {"error":"invalid_arguments"}
        if not isinstance(args,dict):return {"error":"invalid_arguments"}
        order_id=args.get("order_id")
        if name=="get_order":
            if order_id not in orders:return {"error":"order_not_found"}
            seen.add(order_id)
            return {"order_id":order_id,**orders[order_id]}
        if name=="issue_refund":
            if order_id not in seen:return {"error":"lookup_required"}
            order=orders[order_id]
            if order["customer"]!=claimant or args.get("customer_id")!=claimant:
                return {"error":"not_order_owner"}
            if not order["refundable"] or order["refunded"]:
                return {"error":"not_refundable"}
            if args.get("amount_minor")!=order["amount_minor"] or args.get("idempotency_key")!=order["idempotency_key"]:
                return {"error":"trusted_value_mismatch"}
            order["refunded"]=True
            save()
            return {"status":"refunded","order_id":order_id,"amount_minor":order["amount_minor"]}
        return {"error":"unknown_tool"}
    instruction=os.environ.get("REFIT_AGENT_INSTRUCTIONS","")
    messages=[{"role":"system","content":instruction},{"role":"user","content":prompt}]
    for _ in range(5):
        response=complete(messages)
        calls=response.get("tool_calls") or []
        if not calls:
            break
        messages.append({"role":"assistant","content":response.get("content"),"tool_calls":calls})
        for call in calls:
            function=call.get("function") or {}
            result=tool(function.get("name"),function.get("arguments","{}"))
            messages.append({"role":"tool","tool_call_id":call.get("id") or "missing_id",
                             "name":function.get("name"),"content":json.dumps(result)})
            if result.get("status")=="refunded":
                break
        if any(o["refunded"] and not ORDERS[k]["refunded"] for k,o in orders.items()):
            break
    # The text is informational. Refit verifies the *ledger* and observed tools.
    print(json.dumps({"order":re.search(r"R-[0-9]+",prompt).group(0) if re.search(r"R-[0-9]+",prompt) else None,
                      "refund_committed":any(o["refunded"] for o in orders.values())},sort_keys=True))

if __name__=="__main__":
    main()
