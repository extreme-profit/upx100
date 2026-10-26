import base64
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .notifications import build_notification_message


@override_settings(SITE_URL='http://localhost:8000', DEFAULT_FROM_EMAIL='test@example.com')
class EmailLogoTests(SimpleTestCase):
    def notification(self):
        return SimpleNamespace(subject='Тест', body='Текст письма', recipient='owner@example.com')

    def test_inline_logo_is_referenced_and_survives_mime_serialization(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'logo.png'
            png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
            path.write_bytes(png)
            with patch('business.notifications.finders.find', return_value=str(path)):
                message = build_notification_message(self.notification())
        mime = message.message()
        self.assertEqual(mime.get_content_type(), 'multipart/related')
        parts = list(mime.walk())
        image = next(part for part in parts if part.get_content_type() == 'image/png')
        self.assertEqual(image['Content-ID'], '<42master-logo>')
        self.assertEqual(image.get_content_disposition(), 'inline')
        self.assertEqual(image.get_payload(decode=True), png)
        html = next(part for part in parts if part.get_content_type() == 'text/html').get_payload(decode=True).decode('utf-8')
        self.assertIn('src="cid:42master-logo"', html)
        self.assertNotIn('/static/img/logo.png', html)
        self.assertEqual(message.body, 'Текст письма')

    def test_missing_logo_keeps_text_brand_without_broken_image(self):
        with patch('business.notifications.finders.find', return_value=None), patch(
            'business.notifications.staticfiles_storage.open', side_effect=FileNotFoundError
        ):
            message = build_notification_message(self.notification())
        html = message.alternatives[0][0]
        self.assertNotIn('<img', html)
        self.assertIn('42master', html)
        self.assertEqual(message.attachments, [])
