
from fastapi import FastAPI
from pydantic import BaseModel
app=FastAPI(title="Continuity Relay API",version="0.8.0");incidents={}
class Incident(BaseModel):title:str;severity:str
@app.get("/health")
def health():return {"status":"ok"}
@app.post("/incidents")
def create(body:Incident):
 iid=f"inc-{len(incidents)+1}";row={"id":iid,**body.model_dump(),"state":"open","version":1};incidents[iid]=row;return row
@app.post("/incidents/{iid}/complete")
def complete(iid:str):
 # BUG: no auth, no state guard, no evidence, no optimistic concurrency.
 incidents[iid]["state"]="resolved";return incidents[iid]
