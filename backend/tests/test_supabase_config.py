"""
test_supabase_config.py — Phase 6: Supabase connection API

Tests:
  - GET  /api/memory/config/supabase/status  (returns local/supabase)
  - POST /api/memory/config/supabase/connect (validates connection)
  - DELETE /api/memory/config/supabase/connect (disconnect)
"""
import pytest


class TestSupabaseStatus:

    def test_status_requires_auth(self, api_client, base_url):
        api_client.headers.pop("Authorization", None)
        resp = api_client.get(f"{base_url}/api/memory/config/supabase/status")
        assert resp.status_code == 401
        print("✓ Supabase status requires admin auth")

    def test_status_returns_backend_info(self, admin, base_url):
        resp = admin.get(f"{base_url}/api/memory/config/supabase/status")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "backend" in data
        assert data["backend"] in ("local", "supabase")
        assert "connected" in data
        print(f"✓ Supabase status: backend={data['backend']}, connected={data['connected']}")

    def test_default_backend_is_local(self, admin, base_url):
        """Fresh install should default to local backend."""
        resp = admin.get(f"{base_url}/api/memory/config/supabase/status")
        assert resp.status_code == 200
        data = resp.json()
        # If user hasn't connected Supabase, backend should be local
        # (this assertion may fail in prod env — skip if supabase is connected)
        if data["backend"] == "local":
            assert data["connected"] is True
            print("✓ Default backend is local PostgreSQL")
        else:
            pytest.skip("Supabase is already connected in this environment")


class TestSupabaseConnect:

    def test_connect_requires_auth(self, api_client, base_url):
        api_client.headers.pop("Authorization", None)
        resp = api_client.post(f"{base_url}/api/memory/config/supabase/connect", json={
            "supabase_url": "https://test.supabase.co",
            "supabase_db_url": "postgresql://postgres:test@db.test.supabase.co:5432/postgres",
        })
        assert resp.status_code == 401
        print("✓ Supabase connect requires admin auth")

    def test_connect_bad_url_returns_400(self, admin, base_url):
        """Connecting to an invalid Supabase URL should fail gracefully."""
        resp = admin.post(f"{base_url}/api/memory/config/supabase/connect", json={
            "supabase_url": "https://invalid.supabase.co",
            "supabase_db_url": "postgresql://postgres:badpass@db.invalid.supabase.co:5432/postgres",
        })
        # Should return 400 (connection failed), not 500
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "detail" in data or "error" in data
        print(f"✓ Bad Supabase URL returns 400: {data.get('detail', data.get('error', ''))[:80]}")

    def test_connect_missing_fields_returns_422(self, admin, base_url):
        resp = admin.post(f"{base_url}/api/memory/config/supabase/connect", json={
            "supabase_url": "https://test.supabase.co",
            # missing supabase_db_url
        })
        assert resp.status_code == 422
        print("✓ Missing supabase_db_url returns 422")


class TestSupabaseDisconnect:

    def test_disconnect_requires_auth(self, api_client, base_url):
        api_client.headers.pop("Authorization", None)
        resp = api_client.delete(f"{base_url}/api/memory/config/supabase/connect")
        assert resp.status_code == 401
        print("✓ Supabase disconnect requires admin auth")

    def test_disconnect_when_already_local(self, admin, base_url):
        """Disconnecting when already on local PG should succeed or be idempotent."""
        resp = admin.delete(f"{base_url}/api/memory/config/supabase/connect")
        assert resp.status_code in (200, 400), resp.text
        print(f"✓ Disconnect (already local) handled gracefully: {resp.status_code}")
