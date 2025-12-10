from typing import List, Dict
from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api.event import MessageChain

import asyncio
from .llss import LlssCrawler
from pathlib import Path
import json

class LlssSub(Star):
    def __init__(self, context: Context, config : dict):
        super().__init__(context)
        self.config = config
        self.context = context
    
    async def initialize(self):
        self.plugin_name = 'llss_sub'
        self.check_interval = self.config.get("check_interval", 360)
        max_page = self.config.get("max_page", 3)
        base_url = self.config.get("base_url", "https://www.hacg.icu/wp/")
        self.base_dir = StarTools.get_data_dir(self.plugin_name)
        self.temp_dir = self.base_dir / "temp"
        self.sub_sources_file : Path = self.base_dir / "sub_sources.json"
        self.llss = LlssCrawler(site_url=base_url, max_pages=max_page, latest_id_file=str(self.base_dir / "lastest_id.txt"))
        self.sub_check_task = asyncio.create_task(self.start())

    async def start(self):
        while(True):
            await asyncio.sleep(self.check_interval * 60)
            await self._refresh_sub()

    @filter.command("订阅神社")
    async def add_sub(self, event: AstrMessageEvent):
        new_source = event.unified_msg_origin
        sources = self._load_sub_sources()
        sources.append(new_source)
        await self._save_sub_sources(sources)
        yield event.plain_result("订阅成功")

    @filter.command("刷新神社")
    async def refresh_sub(self, event: AstrMessageEvent):
        await self._refresh_sub()
        yield event.plain_result("刷新完成")

    async def _refresh_sub(self):
        sources = self._load_sub_sources()
        if not sources or len(sources) == 0:
            logger.info("无订阅源，无需刷新")
            return
        new_articles : List[Dict] = await self.llss.fetch_latest_articles()
        msg = MessageChain().message(f"琉璃神社更新了{len(new_articles)}篇新文章。\n")
        for source in sources:
            await self.context.send_message(source, msg)
        for article in new_articles:
            title = article.get("title", "无标题")
            url = article.get("url", "")
            desc = article.get("desc", "")
            cover = article.get("cover", None)
            msg = MessageChain().message(f"【标题】：{title}\n【内容】：{desc}\n【链接】：{url}\n")
            msg.url_image(cover)
            for source in sources:
                await self.context.send_message(source, msg)

    def _load_sub_sources(self):
        if not Path.exists(self.sub_sources_file):
            return []
        with open(str(self.sub_sources_file), "r", encoding="utf-8") as f:
            return json.load(f)
        
    async def _save_sub_sources(self, sources):
        with open(str(self.sub_sources_file), "w", encoding="utf-8") as f:
            json.dump(sources, f, ensure_ascii=False, indent=4)

    async def terminate(self):
        if self.sub_check_task and not self.sub_check_task.done():
            self.sub_check_task.cancel()
            try:
                await self.sub_check_task
            except asyncio.CancelledError:
                logger.info(
                    "llss sub task was successfully cancelled during terminate."
                )
            except Exception as e:
                logger.error(
                    f"Error awaiting cancellation of llss sub task: {e}"
                )