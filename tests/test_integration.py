import sqlite3
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from src.integrated import Integration
from src.matching.api import create_app

class PublicationTests(unittest.TestCase):
    def test_publication_lifecycle(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"course.sqlite3"
            def app():
                return create_app(config={},integration=Integration(path,"test-password",{}))
            with TestClient(app()) as client:
                self.assertEqual(client.get("/").status_code,200)
                self.assertIn('id="login"',client.get("/admin").text)
                self.assertEqual(client.get("/admin/api/backup").status_code,401)
                self.assertEqual(client.post("/admin/api/login",json={"username":"tester","password":"test-password"}).status_code,200)
                self.assertIn('id="pubTab"',client.get("/admin").text)
                baseline=client.get("/api/v1/health").json()["company_count"]
                cid=client.post("/admin/api/company/create",json={"fields":{"name":"Publication Test","founders":["Public Founder"],"contact_information":"Private Value"}}).json()["id"]
                self.assertEqual(client.get("/api/v1/companies/"+cid).status_code,404)
                def change():
                    data=client.get("/admin/api/publication/"+cid).json()
                    return {"id":cid,"fields":["founders"],"events":[],"draft":data["draft"],"revision":data["revision"]}
                first=change()
                preview=client.post("/admin/api/publication/preview",json={"changes":[first]})
                self.assertEqual(preview.status_code,200,preview.text)
                self.assertNotIn("Private Value",preview.text)
                self.assertEqual(client.get("/api/v1/companies/"+cid).status_code,404)
                self.assertEqual(client.post("/admin/api/publication/apply",json={"changes":[first]}).status_code,200)
                self.assertEqual(client.post("/admin/api/publication/apply",json={"changes":[first]}).status_code,400)
                detail=client.get("/api/v1/radar/references/"+cid)
                self.assertIn("Public Founder",detail.text)
                self.assertNotIn("Private Value",detail.text)
                self.assertEqual(client.get("/api/v1/health").json()["company_count"],baseline+1)
                self.assertEqual(client.post("/api/v1/recommendations",json={"query":"humanoid robot"}).status_code,200)
                self.assertEqual(client.get("/api/v1/radar/events.csv").status_code,200)
                backup=client.get("/admin/api/backup")
                with sqlite3.connect(":memory:") as copy:
                    copy.deserialize(backup.content)
                    self.assertEqual(copy.execute("SELECT count(*) FROM companies WHERE id=?",(cid,)).fetchone()[0],1)
            with TestClient(app()) as client:
                self.assertEqual(client.get("/api/v1/companies/"+cid).status_code,200)
                client.post("/admin/api/login",json={"username":"tester","password":"test-password"})
                removal={**change(),"withdraw":True}
                self.assertEqual(client.post("/admin/api/publication/apply",json={"changes":[removal]}).status_code,200)
                self.assertEqual(client.get("/api/v1/radar/references/"+cid).status_code,404)
                self.assertEqual(client.get("/api/v1/health").json()["company_count"],baseline)
                self.assertIn("Private Value",client.get("/admin/api/publication/"+cid).text)
