#!/usr/bin/env python3
"""
weixin_publish.py — 微信公众号 API 客户端
AppID/Secret 从环境变量 WEIXIN_APPID / WEIXIN_SECRET 获取
"""

import os
import json
import time

import requests


class WeixinPublisher:
    BASE_URL = "https://api.weixin.qq.com/cgi-bin"

    def __init__(self, config_path: str = "config.json"):
        # 从环境变量获取凭证
        self.appid = os.environ.get("WEIXIN_APPID", "")
        self.secret = os.environ.get("WEIXIN_SECRET", "")

        if not self.appid or not self.secret:
            raise RuntimeError(
                "请设置环境变量:\n"
                "  export WEIXIN_APPID='your_appid'\n"
                "  export WEIXIN_SECRET='your_secret'"
            )

        # 加载非敏感配置
        self.config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)

        # token 缓存
        self._token = None
        self._token_expires = 0

    @staticmethod
    def _truncate_title(title: str, max_chars: int = 64) -> str:
        """截断标题使其字符数不超过微信限制（64字符）"""
        if len(title) <= max_chars:
            return title
        return title[:max_chars]

    @staticmethod
    def _truncate_digest(digest: str, max_chars: int = 120) -> str:
        """截断摘要使其字符数不超过微信限制（120字符）"""
        if len(digest) <= max_chars:
            return digest
        return digest[:max_chars]

    @staticmethod
    def _safe_field(value: str, max_chars: int) -> str:
        """通用字段截断：超限则截断到 max_chars"""
        if len(value) <= max_chars:
            return value
        return value[:max_chars]

    def get_access_token(self) -> str:
        """获取/刷新 access_token，带本地缓存"""
        now = time.time()
        if self._token and now < self._token_expires:
            return self._token

        resp = requests.get(
            f"{self.BASE_URL}/token",
            params={
                "grant_type": "client_credential",
                "appid": self.appid,
                "secret": self.secret
            },
            timeout=10
        )
        data = resp.json()

        if "access_token" not in data:
            raise RuntimeError(f"获取 access_token 失败: {data}")

        self._token = data["access_token"]
        # 提前 5 分钟过期
        self._token_expires = now + data.get("expires_in", 7200) - 300
        return self._token

    def upload_permanent_image(self, image_path: str) -> str:
        """上传永久图片素材（封面图），返回 media_id"""
        token = self.get_access_token()
        url = f"{self.BASE_URL}/material/add_material"

        with open(image_path, "rb") as f:
            resp = requests.post(
                url,
                params={"access_token": token, "type": "image"},
                files={"media": (os.path.basename(image_path), f, "image/png")},
                timeout=30
            )

        data = resp.json()
        if "media_id" not in data:
            raise RuntimeError(f"上传封面图失败: {data}")

        return data["media_id"]

    def upload_content_image(self, image_path_or_url: str) -> str:
        """上传正文内图片，返回微信 URL"""
        token = self.get_access_token()
        url = f"{self.BASE_URL}/media/uploadimg"

        # 如果是 URL，先下载到临时文件
        if image_path_or_url.startswith("http"):
            resp = requests.get(image_path_or_url, timeout=30)
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp.write(resp.content)
            tmp.close()
            image_path = tmp.name
        else:
            image_path = image_path_or_url

        with open(image_path, "rb") as f:
            resp = requests.post(
                url,
                params={"access_token": token},
                files={"media": (os.path.basename(image_path), f, "image/jpeg")},
                timeout=30
            )

        data = resp.json()
        if "url" not in data:
            raise RuntimeError(f"上传正文图片失败: {data}")

        return data["url"]

    def create_draft(self, article: dict) -> str:
        """
        创建草稿，返回 media_id

        article 需包含:
            title, author, digest, content (HTML),
            content_source_url, thumb_media_id
        """
        token = self.get_access_token()
        url = f"{self.BASE_URL}/draft/add"

        payload = {
            "articles": [{
                "title": self._truncate_title(article["title"]),
                "author": self._safe_field(article.get("author", self.config.get("default_author", "")), max_chars=8),
                "digest": self._truncate_digest(article.get("digest", "")),
                "content": article["content"],
                "content_source_url": article.get("content_source_url", ""),
                "thumb_media_id": article["thumb_media_id"],
                "need_open_comment": self.config.get("need_open_comment", 1),
                "only_fans_can_comment": self.config.get("only_fans_can_comment", 0),
            }]
        }

        resp = requests.post(
            url,
            params={"access_token": token},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        data = resp.json()
        if "media_id" not in data:
            raise RuntimeError(f"创建草稿失败: {data}")

        return data["media_id"]

    def update_draft(self, media_id: str, article: dict, index: int = 0) -> bool:
        """
        更新已有草稿中的文章

        参数:
            media_id: 草稿的 media_id（draft/add 返回的）
            article: 同 create_draft 的 article 结构
            index: 多图文消息中的文章位置，默认 0（第一篇）

        返回: True 表示更新成功
        """
        token = self.get_access_token()
        url = f"{self.BASE_URL}/draft/update"

        payload = {
            "media_id": media_id,
            "index": index,
            "articles": {
                "title": self._truncate_title(article["title"]),
                "author": self._safe_field(article.get("author", self.config.get("default_author", "")), max_chars=8),
                "digest": self._truncate_digest(article.get("digest", "")),
                "content": article["content"],
                "content_source_url": article.get("content_source_url", ""),
                "thumb_media_id": article["thumb_media_id"],
                "need_open_comment": self.config.get("need_open_comment", 1),
                "only_fans_can_comment": self.config.get("only_fans_can_comment", 0),
            }
        }

        resp = requests.post(
            url,
            params={"access_token": token},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"更新草稿失败: {data}")

        return True

    def publish(self, media_id: str) -> str:
        """发布草稿，返回 publish_id"""
        token = self.get_access_token()
        url = f"{self.BASE_URL}/freepublish/submit"

        resp = requests.post(
            url,
            params={"access_token": token},
            data=json.dumps({"media_id": media_id}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"发布失败: {data}")

        return data.get("publish_id", "")

    def get_publish_status(self, publish_id: str) -> dict:
        """查询发布状态"""
        token = self.get_access_token()
        url = f"{self.BASE_URL}/freepublish/get"

        resp = requests.post(
            url,
            params={"access_token": token},
            data=json.dumps({"publish_id": publish_id}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        return resp.json()
