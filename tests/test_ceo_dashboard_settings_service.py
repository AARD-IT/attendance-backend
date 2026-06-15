from unittest.mock import MagicMock, patch

from app.services.ceo_dashboard_settings_service import CEODashboardSettingsService


class TestCEODashboardSettingsService:
    def test_get_settings_uses_global_key(self):
        service = CEODashboardSettingsService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '[{"id": "global", "auto_refresh_enabled": true}]'
        mock_response.json.return_value = [{"id": "global", "auto_refresh_enabled": True}]

        with patch("app.services.ceo_dashboard_settings_service.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.get.return_value = mock_response

            result = service.get_settings(user_id="user-123")

        assert result["id"] == "global"
        assert result["auto_refresh_enabled"] is True
        client.get.assert_called_once()
        called_params = client.get.call_args.kwargs["params"]
        assert called_params["id"] == "eq.global"

    def test_upsert_settings_uses_global_key(self):
        service = CEODashboardSettingsService()
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = '[{"id": "global", "auto_refresh_enabled": true}]'
        mock_response.json.return_value = [{"id": "global", "auto_refresh_enabled": True}]

        with patch("app.services.ceo_dashboard_settings_service.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.post.return_value = mock_response

            result = service.upsert_settings({"auto_refresh_enabled": True}, user_id="user-456")

        assert result["id"] == "global"
        assert result["auto_refresh_enabled"] is True
        client.post.assert_called_once()
        body = client.post.call_args.kwargs["json"]
        assert body["id"] == "global"
