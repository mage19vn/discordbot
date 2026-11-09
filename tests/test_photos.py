"""Markdown image rendering, persistent files and the Zalo sendPhoto contract."""

import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace, MethodType
import unittest
from unittest.mock import AsyncMock, patch

from zalo_bot import Bot

import core
import bot_zalo


class MarkdownTests(unittest.TestCase):
    def test_formats_tables_code_and_vietnamese_without_active_html(self):
        html = core.markdown_to_html('# Tiếng Việt\n\n**Đậm**\n\n'
                                     '| A | B |\n|---|---|\n| 1 | 2 |\n\n'
                                     '```cpp\nint x = 1 < 2;\n```\n'
                                     '<script>alert(1)</script>\n'
                                     '![external](https://example.org/image.png)')
        self.assertIn('<h1>Tiếng Việt</h1>', html)
        self.assertIn('<strong>Đậm</strong>', html)
        self.assertIn('<table>', html)
        self.assertIn('1 &lt; 2', html)
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img', html)

    def test_rejects_empty_and_oversize_unicode_input(self):
        for value in (' ', 'ế' * core.MAX_MARKDOWN_BYTES):
            with self.assertRaises(ValueError):
                core.markdown_to_html(value)


class PhotoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.env = patch.dict(os.environ, {
            'MAGOJ_PHOTO_DIR': self.folder.name,
            'MAGOJ_PHOTO_BASE_URL': 'https://images.example.org/bot/',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.api = AsyncMock(return_value='sent')
        self.bot = SimpleNamespace(_send_message=self.api)
        self.bot.send_photo = MethodType(Bot.send_photo, self.bot)

    async def test_pipeline_saves_and_uses_sdk_sendPhoto_with_public_url(self):
        png = b'\x89PNG\r\n\x1a\nimage'
        with patch.object(core, 'markdown_to_png', AsyncMock(return_value=png)) as render:
            result = await core.send_markdown_photo(self.bot, 'chat', '# Hello')
        render.assert_awaited_once_with('# Hello', width=960)
        files = list(Path(self.folder.name).iterdir())
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_bytes(), png)
        self.assertEqual(files[0].suffix, '.png')
        self.api.assert_awaited_once_with('sendPhoto', {
            'chat_id': 'chat', 'photo': 'https://images.example.org/bot/' + files[0].name,
            'caption': 'Ảnh từ Markdown',
        }, reply_to_message_id=None)
        self.assertEqual(result, 'sent')

    async def test_missing_public_url_retains_local_png_and_does_not_send(self):
        with patch.dict(os.environ, {'MAGOJ_PHOTO_BASE_URL': ''}), \
             patch.object(core, 'markdown_to_png', AsyncMock(return_value=b'png')):
            with self.assertRaisesRegex(core.PhotoRenderError, 'Đã lưu PNG'):
                await core.send_markdown_photo(self.bot, 'chat', '# Local')
        self.assertEqual(len(list(Path(self.folder.name).glob('*.png'))), 1)
        self.api.assert_not_awaited()

    async def test_repeated_saves_keep_distinct_files_and_leave_no_temporary_files(self):
        one = await core.save_png(b'first')
        two = await core.save_png(b'second')
        self.assertNotEqual(one, two)
        self.assertEqual(one.read_bytes(), b'first')
        self.assertEqual(two.read_bytes(), b'second')
        self.assertEqual(len(list(Path(self.folder.name).iterdir())), 2)

    async def test_custom_storage_receives_png_and_must_return_https(self):
        publisher = AsyncMock(return_value='https://cdn.example.org/photo.png')
        with patch.object(core, 'markdown_to_png', AsyncMock(return_value=b'png')):
            await core.send_markdown_photo(self.bot, 'chat', 'Hello', publish=publisher)
            publisher.assert_awaited_once_with(b'png')
            self.api.assert_awaited_once()
            self.api.reset_mock()
            publisher.return_value = '/home/container/photo.png'
            with self.assertRaises(core.PhotoRenderError):
                await core.send_markdown_photo(self.bot, 'chat', 'Hello', publish=publisher)
            self.api.assert_not_awaited()

    async def test_render_failure_does_not_publish_or_send(self):
        publisher = AsyncMock()
        with patch.object(core, 'markdown_to_png', AsyncMock(side_effect=core.PhotoRenderError('render'))):
            with self.assertRaises(core.PhotoRenderError):
                await core.send_markdown_photo(self.bot, 'chat', '# H', publish=publisher)
        publisher.assert_not_awaited()
        self.api.assert_not_awaited()

    async def test_invalid_caption_does_not_render(self):
        with patch.object(core, 'markdown_to_png', AsyncMock()) as render:
            with self.assertRaises(ValueError):
                await core.send_markdown_photo(self.bot, 'chat', '# H', caption='x' * 2001)
        render.assert_not_awaited()

    async def test_photo_command_and_recoverable_error(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        adapter = bot_zalo.ZaloAdapter(bot)
        with patch.object(core, 'send_markdown_photo', AsyncMock()) as send:
            await adapter.handle_text('chat', 'user', '/photo # Tiếng Việt')
            send.assert_awaited_once_with(bot, 'chat', '# Tiếng Việt')
            send.side_effect = core.PhotoRenderError('Đã lưu PNG; thiếu URL')
            await adapter.handle_text('chat', 'user', '/photo # Test')
            self.assertIn('Đã lưu PNG', bot.send_message.await_args.kwargs['text'])


@unittest.skipUnless(os.getenv('MAGOJ_TEST_RENDER') == '1',
                     'Set MAGOJ_TEST_RENDER=1 after installing Playwright Chromium')
class ChromiumTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_markdown_html_png_and_height_limit(self):
        png = await core.markdown_to_png('# Xin chào\n\n**Tiếng Việt**\n\n'
                                         '| A | B |\n|---|---|\n| 1 | 2 |', width=800)
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        width, height = struct.unpack('>II', png[16:24])
        self.assertEqual(width, 800)
        self.assertGreater(height, 100)
        with self.assertRaisesRegex(ValueError, 'quá dài'):
            await core.markdown_to_png('Dòng\n\n' * 1000)


if __name__ == '__main__':
    unittest.main()
