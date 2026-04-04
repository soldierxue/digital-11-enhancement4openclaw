#!/usr/bin/env python3
"""
weixin_client.py — 微信公众号 API 客户端（索引相关接口）
AppID/Secret 从环境变量 WEIXIN_APPID / WEIXIN_SECRET 获取
"""

import os
import json
import time

import requests


class WeixinClient:
    BASE_URL = "https://api.weixin.qq.com/cgi-bin"

    def __init__(self):
        self.appid = os.environ.get("WEIXIN_APPID", "")
        self.secret = os.environ.get("WEIXIN_SECRET", "")

        if not self.appid or not self.secret:
            raise RuntimeError(
                "请设置环境变量:\n"
                "  export WEIXIN_APPID='your_appid'\n"
                "  export WEIXIN_SECRET='your_secret'"
            )

        self._token = None
        self._token_expires = 0

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
        self._token_expires = now + data.get("expires_in", 7200) - 300
        return self._token

    def get_published_articles(self, offset: int = 0, count: int = 20) -> dict:
        """
        获取永久图文素材列表（分页）— 旧体系
        material/batchget_material (type=news)
        """
        token = self.get_access_token()
        url = f"{self.BASE_URL}/material/batchget_material"

        resp = requests.post(
            url,
            params={"access_token": token},
            data=json.dumps({
                "type": "news",
                "offset": offset,
                "count": min(count, 20),
            }, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        resp.encoding = "utf-8"
        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"获取图文素材列表失败: {data}")

        return data

    def get_admin_articles(self, cookie: str, token: str,
                          fakeid: str = "", begin: int = 0,
                          count: int = 5) -> dict:
        """
        通过微信公众号后台管理接口获取文章列表（全量）
        mp.weixin.qq.com/cgi-bin/appmsg?action=list_ex
        需要浏览器 cookie + token 认证
        """
        url = "https://mp.weixin.qq.com/cgi-bin/appmsg"
        headers = {
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        }
        params = {
            "action": "list_ex",
            "begin": str(begin),
            "count": str(min(count, 5)),
            "type": "9",
            "token": token,
            "lang": "zh_CN",
            "f": "json",
            "ajax": "1",
        }
        if fakeid:
            params["fakeid"] = fakeid

        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.encoding = "utf-8"
        data = resp.json()

        base_resp = data.get("base_resp", {})
        ret = base_resp.get("ret", 0)
        if ret == 200013:
            raise RuntimeError("频率限制 (200013)，请等待后重试")
        if ret != 0:
            raise RuntimeError(f"后台接口错误: ret={ret}, err_msg={base_resp.get('err_msg', '')}")

        return data

    def get_freepublish_articles(self, offset: int = 0, count: int = 20,
                                 no_content: int = 1) -> dict:
        """
        获取已发布文章列表（分页）— 新体系
        freepublish/batchget（订阅号通常 48001 无权限）
        """
        token = self.get_access_token()
        url = f"{self.BASE_URL}/freepublish/batchget"

        resp = requests.post(
            url,
            params={"access_token": token},
            data=json.dumps({
                "offset": offset,
                "count": min(count, 20),
                "no_content": no_content,
            }, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        resp.encoding = "utf-8"
        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"获取已发布文章列表失败: {data}")

        return data
