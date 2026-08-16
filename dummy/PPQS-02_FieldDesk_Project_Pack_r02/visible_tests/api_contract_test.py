
import json, os, urllib.error, urllib.request, unittest
BASE=os.environ.get("FIELDDESK_BASE_URL","http://127.0.0.1:8000")
class VisibleAPIContract(unittest.TestCase):
 def request(self,path,method="GET",body=None,headers=None):
  data=None if body is None else json.dumps(body).encode(); req=urllib.request.Request(BASE+path,data=data,method=method,headers={"Content-Type":"application/json",**(headers or {})})
  try:
   with urllib.request.urlopen(req,timeout=5) as r:return r.status,json.loads(r.read() or b"{}")
  except urllib.error.HTTPError as e:return e.code,json.loads(e.read() or b"{}")
 def test_health(self):
  status,body=self.request("/health");self.assertEqual(status,200);self.assertIn(body.get("status"),{"ok","degraded"})
 def test_unauthenticated_work_orders_denied(self):
  status,_=self.request("/api/v1/work-orders");self.assertIn(status,{401,403})
 def test_invalid_transition_rejected(self):
  status,_=self.request("/api/v1/work-orders/demo/transition","POST",{"to":"completed"},{"Authorization":"Bearer ppqs-technician-demo"});self.assertIn(status,{400,403,404,409,422})
if __name__=="__main__":unittest.main()
