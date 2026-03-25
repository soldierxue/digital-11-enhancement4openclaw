#!/usr/bin/env python3
"""
channels_uploader.py — 视频号创作者中心页面自动化
通过 CDP 操作 channels.weixin.qq.com 完成视频上传和表单填写

注意：视频号创作者中心的前端结构可能随微信更新而变化，
选择器需要定期维护。本模块提供基础框架和选择器发现机制。
"""

import os
import time
import json

from cdp_client import CDPClient


class ChannelsUploader:
    """视频号上传自动化"""

    # 轮询间隔（秒）
    POLL_INTERVAL = 3
    # 上传超时（秒）
    UPLOAD_TIMEOUT = 300

    def __init__(self, cdp: CDPClient):
        self.cdp = cdp

    def check_login_status(self) -> bool:
        """检查是否已登录视频号创作者中心"""
        result = self.cdp.evaluate("""
            (() => {
                // 检查是否在登录页
                const url = window.location.href;
                if (url.includes('/login')) return JSON.stringify({logged_in: false, reason: 'login_page'});

                // 检查是否有用户头像或昵称元素（已登录标识）
                const avatar = document.querySelector('.finder-avatar, .avatar, [class*="avatar"]');
                const nickname = document.querySelector('.finder-nickname, .nickname, [class*="nickname"]');
                if (avatar || nickname) return JSON.stringify({logged_in: true});

                // 检查页面是否有发布按钮（已登录标识）
                const publishBtn = document.querySelector('[class*="publish"], [class*="create"]');
                if (publishBtn) return JSON.stringify({logged_in: true});

                return JSON.stringify({logged_in: false, reason: 'no_login_indicator'});
            })()
        """)
        if isinstance(result, dict):
            return result.get("logged_in", False)
        return False

    def discover_upload_selectors(self) -> dict:
        """
        动态发现页面上的关键元素选择器。
        视频号前端可能更新，此方法帮助适配新结构。
        """
        result = self.cdp.evaluate("""
            (() => {
                const selectors = {};

                // 查找 file input（视频上传入口）
                const fileInputs = document.querySelectorAll('input[type="file"]');
                selectors.file_inputs = Array.from(fileInputs).map(el => ({
                    accept: el.getAttribute('accept') || '',
                    id: el.id || '',
                    className: el.className || '',
                    name: el.name || '',
                    parentClass: el.parentElement?.className || ''
                }));

                // 查找标题输入框
                const titleInputs = document.querySelectorAll(
                    'input[placeholder*="标题"], textarea[placeholder*="标题"], ' +
                    '[class*="title"] input, [class*="title"] textarea, ' +
                    '[contenteditable][class*="title"]'
                );
                selectors.title_inputs = titleInputs.length;

                // 查找描述输入框
                const descInputs = document.querySelectorAll(
                    'textarea[placeholder*="描述"], textarea[placeholder*="说点什么"], ' +
                    '[class*="desc"] textarea, [contenteditable][class*="desc"]'
                );
                selectors.desc_inputs = descInputs.length;

                // 查找发布/草稿按钮
                const buttons = document.querySelectorAll('button');
                selectors.buttons = Array.from(buttons).slice(0, 20).map(b => ({
                    text: b.textContent?.trim().substring(0, 30) || '',
                    className: b.className || ''
                }));

                return JSON.stringify(selectors);
            })()
        """)
        return result if isinstance(result, dict) else {}

    def upload_video(self, video_path: str) -> bool:
        """
        上传视频文件到视频号创作者中心

        通过 CDP DOM.setFileInputFiles 注入文件路径到 input[type=file]
        """
        abs_path = os.path.abspath(video_path)
        if not os.path.isfile(abs_path):
            print(f"  ✗ 视频文件不存在: {abs_path}")
            return False

        size_mb = os.path.getsize(abs_path) / (1024 * 1024)
        print(f"  📁 视频文件: {abs_path} ({size_mb:.1f} MB)")

        # 获取 DOM 根节点
        doc = self.cdp.send("DOM.getDocument", {"depth": 0})
        root_id = doc["result"]["root"]["nodeId"]

        # 查找视频 file input
        # 视频号创作者中心通常有 accept="video/*" 的 input
        file_input = self.cdp.send("DOM.querySelector", {
            "nodeId": root_id,
            "selector": "input[type='file'][accept*='video']"
        })
        node_id = file_input.get("result", {}).get("nodeId", 0)

        if not node_id:
            # 回退：查找任意 file input
            file_input = self.cdp.send("DOM.querySelector", {
                "nodeId": root_id,
                "selector": "input[type='file']"
            })
            node_id = file_input.get("result", {}).get("nodeId", 0)

        if not node_id:
            print("  ✗ 未找到文件上传入口")
            print("  提示: 请确保已导航到视频号创作者中心的发布页面")
            selectors = self.discover_upload_selectors()
            print(f"  页面元素: {json.dumps(selectors, ensure_ascii=False, indent=2)}")
            return False

        # 注入文件
        print("  ▶ 注入视频文件...")
        self.cdp.send("DOM.setFileInputFiles", {
            "nodeId": node_id,
            "files": [abs_path]
        })

        # 等待上传完成
        return self._wait_upload_complete()

    def _wait_upload_complete(self) -> bool:
        """轮询等待视频上传完成"""
        print("  ▶ 等待上传完成...")
        start = time.time()

        while time.time() - start < self.UPLOAD_TIMEOUT:
            status = self.cdp.evaluate("""
                (() => {
                    // 查找上传进度指示
                    const progressEl = document.querySelector(
                        '[class*="progress"], [class*="upload-progress"], .progress-bar'
                    );
                    // 查找上传完成指示
                    const doneEl = document.querySelector(
                        '[class*="upload-success"], [class*="upload-done"], ' +
                        '[class*="video-preview"], [class*="video-cover"]'
                    );
                    // 查找错误提示
                    const errorEl = document.querySelector(
                        '[class*="upload-error"], [class*="upload-fail"], .error-tip'
                    );

                    if (errorEl) {
                        return JSON.stringify({
                            status: 'error',
                            message: errorEl.textContent?.trim() || '上传失败'
                        });
                    }
                    if (doneEl) {
                        return JSON.stringify({status: 'done'});
                    }
                    if (progressEl) {
                        const text = progressEl.textContent?.trim() || '';
                        const style = progressEl.style?.width || '';
                        return JSON.stringify({
                            status: 'uploading',
                            text: text,
                            width: style
                        });
                    }
                    return JSON.stringify({status: 'waiting'});
                })()
            """)

            if isinstance(status, dict):
                s = status.get("status", "waiting")
                if s == "done":
                    print("  ✓ 视频上传完成")
                    return True
                elif s == "error":
                    print(f"  ✗ 上传失败: {status.get('message', '')}")
                    return False
                elif s == "uploading":
                    elapsed = int(time.time() - start)
                    print(f"  ⏳ 上传中... {status.get('text', '')} ({elapsed}s)")

            time.sleep(self.POLL_INTERVAL)

        print(f"  ✗ 上传超时 ({self.UPLOAD_TIMEOUT}s)")
        return False

    def fill_title(self, title: str) -> bool:
        """填写视频标题"""
        print(f"  ▶ 填写标题: {title}")
        result = self.cdp.evaluate(f"""
            (() => {{
                const title = {json.dumps(title)};
                // 尝试多种选择器
                const selectors = [
                    'input[placeholder*="标题"]',
                    'textarea[placeholder*="标题"]',
                    '[class*="title-input"] input',
                    '[class*="title-input"] textarea',
                    '[class*="title"] [contenteditable="true"]',
                ];
                for (const sel of selectors) {{
                    const el = document.querySelector(sel);
                    if (el) {{
                        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {{
                            el.focus();
                            el.value = title;
                            el.dispatchEvent(new Event('input', {{bubbles: true}}));
                            el.dispatchEvent(new Event('change', {{bubbles: true}}));
                        }} else {{
                            el.focus();
                            el.textContent = title;
                            el.dispatchEvent(new Event('input', {{bubbles: true}}));
                        }}
                        return JSON.stringify({{success: true, selector: sel}});
                    }}
                }}
                return JSON.stringify({{success: false, reason: 'no_title_input'}});
            }})()
        """)
        success = isinstance(result, dict) and result.get("success", False)
        if success:
            print(f"  ✓ 标题已填写 (via {result.get('selector', '')})")
        else:
            print("  ⚠ 未找到标题输入框，可能需要更新选择器")
        return success

    def fill_description(self, desc: str) -> bool:
        """填写视频描述"""
        print(f"  ▶ 填写描述 ({len(desc)} 字)")
        result = self.cdp.evaluate(f"""
            (() => {{
                const desc = {json.dumps(desc)};
                const selectors = [
                    'textarea[placeholder*="描述"]',
                    'textarea[placeholder*="说点什么"]',
                    'textarea[placeholder*="添加描述"]',
                    '[class*="desc"] textarea',
                    '[class*="description"] textarea',
                    '[class*="desc"] [contenteditable="true"]',
                ];
                for (const sel of selectors) {{
                    const el = document.querySelector(sel);
                    if (el) {{
                        if (el.tagName === 'TEXTAREA') {{
                            el.focus();
                            el.value = desc;
                            el.dispatchEvent(new Event('input', {{bubbles: true}}));
                            el.dispatchEvent(new Event('change', {{bubbles: true}}));
                        }} else {{
                            el.focus();
                            el.textContent = desc;
                            el.dispatchEvent(new Event('input', {{bubbles: true}}));
                        }}
                        return JSON.stringify({{success: true, selector: sel}});
                    }}
                }}
                return JSON.stringify({{success: false, reason: 'no_desc_input'}});
            }})()
        """)
        success = isinstance(result, dict) and result.get("success", False)
        if success:
            print(f"  ✓ 描述已填写")
        else:
            print("  ⚠ 未找到描述输入框")
        return success

    def upload_cover(self, cover_path: str) -> bool:
        """上传自定义封面"""
        abs_path = os.path.abspath(cover_path)
        if not os.path.isfile(abs_path):
            print(f"  ✗ 封面文件不存在: {abs_path}")
            return False

        print(f"  ▶ 上传封面: {abs_path}")

        doc = self.cdp.send("DOM.getDocument", {"depth": 0})
        root_id = doc["result"]["root"]["nodeId"]

        # 查找图片 file input（封面上传）
        file_input = self.cdp.send("DOM.querySelector", {
            "nodeId": root_id,
            "selector": "input[type='file'][accept*='image']"
        })
        node_id = file_input.get("result", {}).get("nodeId", 0)

        if not node_id:
            print("  ⚠ 未找到封面上传入口，将使用视频默认截图")
            return False

        self.cdp.send("DOM.setFileInputFiles", {
            "nodeId": node_id,
            "files": [abs_path]
        })
        time.sleep(3)
        print("  ✓ 封面已上传")
        return True

    def save_draft(self) -> bool:
        """点击保存草稿按钮"""
        print("  ▶ 保存草稿...")
        result = self.cdp.evaluate("""
            (() => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    const text = btn.textContent?.trim() || '';
                    if (text.includes('草稿') || text.includes('保存') || text.includes('存草稿')) {
                        btn.click();
                        return JSON.stringify({success: true, text: text});
                    }
                }
                return JSON.stringify({success: false, reason: 'no_draft_button'});
            })()
        """)
        success = isinstance(result, dict) and result.get("success", False)
        if success:
            print(f"  ✓ 已点击「{result.get('text', '')}」")
            time.sleep(3)
        else:
            print("  ⚠ 未找到草稿按钮")
        return success

    def publish(self) -> bool:
        """点击发布按钮"""
        print("  ▶ 发布视频...")
        result = self.cdp.evaluate("""
            (() => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    const text = btn.textContent?.trim() || '';
                    if (text === '发表' || text === '发布' || text === '发布视频') {
                        btn.click();
                        return JSON.stringify({success: true, text: text});
                    }
                }
                return JSON.stringify({success: false, reason: 'no_publish_button'});
            })()
        """)
        success = isinstance(result, dict) and result.get("success", False)
        if success:
            print(f"  ✓ 已点击「{result.get('text', '')}」")
            time.sleep(5)
        else:
            print("  ⚠ 未找到发布按钮")
        return success
