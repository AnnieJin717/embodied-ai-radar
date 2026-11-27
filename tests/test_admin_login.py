"""Exercise the same form/cookie flow used by a browser, without real API calls."""
import json
import tempfile
import unittest
from http.cookiejar import CookieJar
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from src.admin.server import make_server


class LoginTests(unittest.TestCase):
    def test_form_wrong_password_login_refresh_and_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = make_server(("127.0.0.1", 0), Path(tmp) / "test.db", "fixture-password")
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            root = f"http://127.0.0.1:{server.server_port}"
            cookies = CookieJar()
            client = build_opener(HTTPCookieProcessor(cookies))

            def post(data, origin=None):
                headers = {"Content-Type": "application/json"}
                if origin:
                    headers["Origin"] = origin
                return client.open(Request(root + "/api/login", json.dumps(data).encode(), headers), timeout=5)

            try:
                with client.open(root, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertNotIn("WWW-Authenticate", response.headers)
                    self.assertIn('id="login"', response.read().decode())
                for body in [{"username": "tester", "password": "wrong"}, {"username": [], "password": 1}]:
                    with self.assertRaises(HTTPError) as caught:
                        post(body)
                    self.assertEqual(caught.exception.code, 401)
                    self.assertNotIn("WWW-Authenticate", caught.exception.headers)
                    self.assertIn("error", json.load(caught.exception))
                with self.assertRaises(HTTPError) as caught:
                    post({"username": "tester", "password": "fixture-password"}, "https://other.example")
                self.assertEqual(caught.exception.code, 400)
                with post({"username": "tester", "password": "fixture-password"}, root) as response:
                    self.assertTrue(json.load(response)["ok"])
                    header = response.headers["Set-Cookie"]
                    for flag in ["HttpOnly", "SameSite=Strict", "Max-Age=28800"]:
                        self.assertIn(flag, header)
                self.assertEqual(len(list(cookies)), 1)
                with client.open(root + "/api/session", timeout=5) as response:
                    self.assertEqual(json.load(response)["username"], "tester")
                # The post-login navigation and subsequent refreshes must all work.
                for _ in range(3):
                    with client.open(root + "/", timeout=5) as response:
                        page = response.read().decode()
                        self.assertIn('id="companyView"', page)
                        self.assertNotIn('id="login"', page)
                    with client.open(root + "/api/companies", timeout=5) as response:
                        self.assertEqual(len(json.load(response)), 60)
                    with client.open(root + "/api/candidates", timeout=5) as response:
                        self.assertIsInstance(json.load(response), list)
                stranger = build_opener()
                with self.assertRaises(HTTPError) as caught:
                    stranger.open(root + "/api/companies", timeout=5)
                self.assertEqual(caught.exception.code, 401)
                with client.open(root + "/healthz", timeout=5) as response:
                    self.assertEqual(json.load(response)["version"], "form-login-v2")
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
