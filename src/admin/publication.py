"""Immutable customer-visible company editions, including explicitly selected events."""
import hashlib
import json
from functools import lru_cache
from collections import defaultdict

from . import store
from .export import ARRAYS
from ..matching.company_repository import JsonCompanyRepository, safe_url

PUBLIC = ("headquarters","website","founded_date","founders","founder_education","founder_work_background",
          "business_description","products","primary_tracks","sub_tracks","technology_routes","application_scenarios",
          "funding_stage","funding_history","historical_investors","valuation","major_customers","business_models",
          "shipments","revenue","employee_scale","contact_information")
BASE = ("headquarters","website","business_description","products","sub_tracks","technology_routes","application_scenarios",
        "funding_stage","funding_history","historical_investors","valuation")
ARRAY_FIELDS = ARRAYS | {"founders","primary_tracks","sub_tracks","technology_routes","application_scenarios"}
LATEST = """SELECT e.* FROM editions e JOIN (SELECT company_id,MAX(id) id FROM editions GROUP BY company_id) i ON e.id=i.id"""
NEWS_KIND = {"product_launch":"launch","research_plan":"plan","funding":"funding","prototype":"prototype"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def initialize(db):
    db.executescript("""CREATE TABLE IF NOT EXISTS editions (
        id INTEGER PRIMARY KEY, company_id TEXT NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL,
        created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS editions_company ON editions(company_id,id);""")
    db.execute("BEGIN IMMEDIATE")
    if db.execute("SELECT id FROM editions LIMIT 1").fetchone():
        return
    seed = JsonCompanyRepository(store.DATA)
    for company in seed.companies():
        cid = company["id"]
        row = project(company, BASE, [])
        row.update(urls=seed.urls(cid), funding=seed.funding(cid), status=seed.status(cid))
        row["company"]["provenance"] = public_origin(company, BASE)
        save(db, cid, row, "client baseline")


def public_origin(company, fields):
    origin = company.get("provenance", {})
    return {"workbook":origin.get("workbook",""),"sheet":origin.get("sheet",""),
            "cells":{k:v for k,v in origin.get("cells",{}).items() if k in fields}}


def project(company, fields, events):
    if set(fields)-set(PUBLIC):
        raise ValueError("Unknown public field")
    values = {k:company[k] for k in fields if company.get(k) is not None}
    profile = {"id":company["id"],"name":company["name"], **values}
    urls = [url for k,url in company.get("admin_sources",{}).items() if k in fields and safe_url(url)]
    return {"company":profile,"fields":list(fields),"events":events,"urls":sorted(set(urls)),
            "funding":[],"status":"published"}


def save(db, cid, row, actor):
    db.execute("INSERT INTO editions(company_id,payload,actor) VALUES (?,?,?)",(cid,store.encode(row),actor))


def workspace(db, cid):
    entry = db.execute("SELECT payload FROM companies WHERE id=?", (cid,)).fetchone()
    if not entry:
        raise ValueError("Unknown company")
    company = json.loads(entry[0])
    events = [json.loads(r[0]) for r in db.execute("SELECT payload FROM events WHERE company_id=? ORDER BY source_key,type,summary",(cid,))]
    last = db.execute("SELECT id,payload FROM editions WHERE company_id=? ORDER BY id DESC LIMIT 1",(cid,)).fetchone()
    return {"company":company,"events":{digest(e):e for e in events},"available":list(PUBLIC),
            "history":[{"revision":r["id"],"created":r["created"],"actor":r["actor"]} for r in db.execute(
                "SELECT id,created,actor FROM editions WHERE company_id=? ORDER BY id DESC LIMIT 12",(cid,))],
            "live":json.loads(last["payload"]) if last else None,"revision":last["id"] if last else 0,
            "draft":digest([company,events])}


def candidate(state, change):
    if change["revision"] != state["revision"] or change["draft"] != state["draft"]:
        raise ValueError("This company changed. Reload the preview before publishing.")
    if change.get("withdraw"):
        return None
    events = []
    for key in change["events"]:
        if key not in state["events"]:
            raise ValueError("Unknown event")
        event = state["events"][key]
        events.append({k:event.get(k) for k in ("type","summary","url","published_at","event_date","evidence")})
    company = state["company"]
    fields = change["fields"]
    row = project(company, fields, events)
    seed = seed_by_id().get(company["id"])
    if seed:
        unchanged = [k for k in fields if company.get(k)==seed.get(k)]
        row["company"]["provenance"] = public_origin(seed, unchanged)
        if "funding_history" in unchanged:
            row["funding"] = seed_repo().funding(company["id"])
        if set(BASE)<=set(unchanged):
            row["urls"] = sorted(set(row["urls"]+seed_repo().urls(company["id"])))
    return row


@lru_cache(maxsize=1)
def seed_repo():
    return JsonCompanyRepository(store.DATA)

@lru_cache(maxsize=1)
def seed_by_id():
    return {r["id"]:r for r in seed_repo().companies()}


def apply(db, changes, actor, preview=False):
    if not isinstance(changes,list) or not 1<=len(changes)<=100 or len({c["id"] for c in changes})!=len(changes):
        raise ValueError("Select distinct companies (up to 100).")
    db.execute("BEGIN IMMEDIATE")
    rows=[]
    for change in changes:
        cid=change["id"]
        state=workspace(db,cid)
        if change.get("restore"):
            if state["revision"]!=change["revision"] or state["draft"]!=change["draft"]:
                raise ValueError("Reload the preview before restoring.")
            old=db.execute("SELECT payload FROM editions WHERE id=? AND company_id=?", (change["restore"],cid)).fetchone()
            if old is None:
                raise ValueError("Unknown published revision")
            row=json.loads(old[0])
        else:
            row=candidate(state,change)
        rows.append(row)
        if not preview:
            save(db,cid,row,actor)
    return rows


class PublishedRepository(JsonCompanyRepository):
    def __init__(self, editions):
        self._companies={}
        self._labels=defaultdict(list)
        self._urls=defaultdict(list)
        self._funding=defaultdict(list)
        self.statuses={}
        self.articles={}
        for entry in editions:
            row=json.loads(entry["payload"])
            if row is None:
                continue
            raw=row["company"]
            c={k:([] if k in ARRAY_FIELDS else None) for k in (*PUBLIC,"investment_thesis","scope_notes","diligence_questions")}
            c.update(raw)
            for k in ARRAY_FIELDS:
                if not isinstance(c.get(k),list):
                    c[k]=[str(c[k])] if c.get(k) else []
            for k in ("headquarters","funding_stage","business_description","website"):
                if c.get(k) is not None and not isinstance(c[k],str):
                    c[k]=str(c[k])
            c.setdefault("provenance",public_origin({},[]))
            cid=c["id"]
            self._companies[cid]=c
            self._funding[cid]=row["funding"]
            self._urls[cid]=row["urls"]
            self.statuses[cid]=row["status"]
            c["published_fields"]={k:raw[k] for k in row["fields"] if k in raw and raw[k] not in (None,[], "")}
            for k in ("sub_tracks","application_scenarios","technology_routes"):
                self._labels[k].extend(c[k])
            for index,e in enumerate(row["events"]):
                url=e["url"] if safe_url(e.get("url")) else "/company-matching#"+cid+"-"+str(index)
                article=self.articles.setdefault(url,{"title":e["summary"],"published_at":e["published_at"],
                    "url":url,"events":[],"keywords":[],"topic_focus":"primary"})
                article["events"].append({"subject":c["name"],"product":None,"kind":NEWS_KIND[e["type"]],
                    "evidence":e.get("evidence") or e["summary"],"event_date":e["event_date"],
                    "status":"supported","time_text":None,"evidence_field":"published"})
    def status(self,company_id):
        return self.statuses[company_id]
