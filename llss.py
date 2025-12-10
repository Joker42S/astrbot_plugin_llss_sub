#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from astrbot.api import logger

import asyncio
import aiohttp
import async_timeout
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
import re
import time
from typing import Optional, List, Dict


class LlssCrawler:
    def __init__(
        self,
        site_url: str = "https://www.hacg.icu/wp/",
        latest_id_file: str = "latest_id.txt",
        max_pages: int = 3,
        retry: int = 3,
        retry_delay: float = 1.0
    ):
        """
        :param site_url: 网站地址
        :param latest_id_file: 用来记录最新 ID 的文件
        :param max_pages: 正常抓取时最多抓取多少页
        :param retry: 网络请求失败后的重试次数
        :param retry_delay: 重试的初始等待时间（指数退避）
        """
        self.site_url = site_url.rstrip("/")
        self.latest_id_file = latest_id_file
        self.max_pages = max_pages
        self.retry = retry
        self.retry_delay = retry_delay

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }

    # -------------------- 工具区 --------------------
    def _extract_id(self, url: str) -> Optional[int]:
        m = re.search(r'/(\d+)\.html', url)
        return int(m.group(1)) if m else None

    def _load_latest_id(self) -> Optional[int]:
        if not os.path.exists(self.latest_id_file):
            return None
        try:
            with open(self.latest_id_file, "r") as f:
                return int(f.read().strip())
        except:
            return None

    def _save_latest_id(self, id_val: int):
        with open(self.latest_id_file, "w") as f:
            f.write(str(id_val))

    # ------------------ 异步请求 + 重试 ------------------
    async def _fetch_html(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """带重试机制的异步 GET 请求"""
        delay = self.retry_delay

        for attempt in range(1, self.retry + 1):
            try:
                async with async_timeout.timeout(60):
                    async with session.get(url, headers=self.headers) as resp:
                        resp.raise_for_status()
                        return await resp.text()

            except Exception as e:
                logger.info(f"[获取琉璃神社内容失败 {attempt}/{self.retry}] 请求失败: {url} -> {e}")

                if attempt < self.retry:
                    await asyncio.sleep(delay)
                    delay *= 2  # 指数退避

        return None

    async def _fetch_page(self, session: aiohttp.ClientSession, page_url: str) -> List:
        html = await self._fetch_html(session, page_url)
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        return soup.select("article")

    # ------------------ 主逻辑（异步） ------------------
    async def fetch_latest_articles(self) -> List[Dict]:
        #返回数据格式: [{"title": str, "url": str, "id": int, "cover": str, "desc": str}, ...]
        logger.info("开始检查琉璃神社更新...")
        latest_id = self._load_latest_id()
        results = []
        max_new_id = latest_id or 0

        # ------------------ 首次启动（仅抓第一篇） ------------------
        if latest_id is None:
            logger.info("首次启动，只抓取首页第一篇文章。")

            async with aiohttp.ClientSession() as session:
                articles = await self._fetch_page(session, self.site_url)

            if not articles or len(articles) == 0:
                logger.info("首页抓取失败。")
                return results

            art = articles[1]
            a = (
                art.select_one("header h1 a")
                or art.select_one("h1 a")
                or art.select_one("a")
            )
            if not a:
                logger.error("首页第一篇文章无法解析")
                return results

            url = a.get("href", "")
            id_val = self._extract_id(url)
            if id_val is None:
                logger.error("无法解析文章 ID")
                return results

            img = art.select_one("div p img")
            cover = img["src"] if img else None

            desc = art.select_one("div p").get_text(separator="\n", strip=True)

            data = {"title": a.get_text(strip=True), "url": url, "id": id_val, "cover": cover, "desc": desc}
            results.append(data)

            self._save_latest_id(id_val)
            logger.info(f"首次抓取完成，保存 ID = {id_val}")

            return results

        # ------------------ 多页抓取 ------------------
        async with aiohttp.ClientSession() as session:
            for page_index in range(1, self.max_pages + 1):
                page_url = (
                    self.site_url if page_index == 1 else f"{self.site_url}/page/{page_index}/"
                )
                logger.info(f"\n抓取第 {page_index} 页：{page_url}")

                articles = await self._fetch_page(session, page_url)
                if not articles:
                    logger.info("该页无文章，停止。")
                    break

                new_on_page = 0

                for art in articles:
                    a = (
                        art.select_one("header h1 a")
                        or art.select_one("h1 a")
                        or art.select_one("a")
                    )
                    if not a:
                        continue

                    title = a.get_text(strip=True)
                    if not title or title == "":
                        continue

                    url = a.get("href", "")
                    id_val = self._extract_id(url)
                    if id_val is None:
                        logger.info(f"无法解析文章ID，跳过：{url}")
                        continue

                    # 已经抓过
                    if id_val <= latest_id:
                        continue

                    img = art.select_one("div p img")
                    cover = img["src"] if img else None

                    desc = art.select_one("div p").get_text(separator="\n", strip=True)

                    data = {"title": title, "url": url, "id": id_val, "cover": cover, "desc": desc}
                    results.append(data)
                    logger.info(f"发现新文章：{title} (ID={id_val})")

                    new_on_page += 1
                    if id_val > max_new_id:
                        max_new_id = id_val

                if new_on_page == 0:
                    logger.info(f"第 {page_index} 页无新增文章，停止。")
                    break
                await asyncio.sleep(3)

        if max_new_id > latest_id:
            self._save_latest_id(max_new_id)
        return results