# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：  
# 1. 不得用于任何商业用途。  
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。  
# 3. 不得进行大规模爬取或对平台造成运营干扰。  
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。   
# 5. 不得用于任何非法或不当的用途。
#   
# 详细许可条款请参阅项目根目录下的LICENSE文件。  
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。  


import asyncio
import os
import random
from asyncio import Task
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import (BrowserContext, BrowserType, Page,
                                  async_playwright)

import config
from base.base_crawler import AbstractCrawler
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import toutiao as toutiao_store
from tools import utils
from var import crawler_type_var, source_keyword_var

from .client import ToutiaoClient
from .exception import DataFetchError
from .field import PublishTimeType
from .login import ToutiaoLogin


class ToutiaoCrawler(AbstractCrawler):
    context_page: Page
    toutiao_client: ToutiaoClient
    browser_context: BrowserContext

    def __init__(self) -> None:
        self.index_url = "https://www.toutiao.com"

    async def start(self) -> None:
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = self.format_proxy_info(ip_proxy_info)

        async with async_playwright() as playwright:
            # Launch a browser context.
            chromium = playwright.chromium
            self.browser_context = await self.launch_browser(
                chromium,
                None,
                user_agent=None,
                headless=config.HEADLESS
            )
            # stealth.min.js is a js script to prevent the website from detecting the crawler.
            await self.browser_context.add_init_script(path="libs/stealth.min.js")
            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url)

            self.toutiao_client = await self.create_toutiao_client(httpx_proxy_format)
            if not await self.toutiao_client.pong(browser_context=self.browser_context):
                login_obj = ToutiaoLogin(
                    login_type=config.LOGIN_TYPE,
                    login_phone="",  # you phone number
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES
                )
                await login_obj.begin()
                await self.toutiao_client.update_cookies(browser_context=self.browser_context)
            crawler_type_var.set(config.CRAWLER_TYPE)
            if config.CRAWLER_TYPE == "search":
                # Search for notes and retrieve their comment information.
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                # Get the information and comments of the specified post
                await self.get_specified_posts()
            elif config.CRAWLER_TYPE == "creator":
                # Get the information and comments of the specified creator
                await self.get_creators_and_posts()

            utils.logger.info("[ToutiaoCrawler.start] Toutiao Crawler finished ...")

    async def search(self) -> None:
        utils.logger.info("[ToutiaoCrawler.search] Begin search toutiao keywords")
        raise Exception("not implemented.")

    async def get_specified_posts(self):
        """Get the information and comments of the specified post"""
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [
            self.get_post_detail(id=id, semaphore=semaphore) for id in config.TOUTIAO_SPECIFIED_ID_LIST
        ]
        post_details = await asyncio.gather(*task_list)
        for post_detail in post_details:
            if post_detail is not None:
                await toutiao_store.update_toutiao_post(post_detail)
        await self.batch_get_note_comments(config.TOUTIAO_SPECIFIED_ID_LIST)

    async def get_post_detail(self, id: str, semaphore: asyncio.Semaphore) -> Any:
        """Get note detail"""
        async with semaphore:
            try:
                return await self.toutiao_client.get_post_by_id(id)
            except DataFetchError as ex:
                utils.logger.error(f"[ToutiaoCrawler.get_post_detail] Get post detail error: {ex}")
                return None
            except KeyError as ex:
                utils.logger.error(
                    f"[ToutiaoCrawler.get_post_detail] have not fund note detail post_id:{id}, err: {ex}")
                return None

    async def batch_get_note_comments(self, post_list: List[str]) -> None:
        """
        Batch get note comments
        """
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info(f"[ToutiaoCrawler.batch_get_note_comments] Crawling comment mode is not enabled")
            return

        task_list: List[Task] = []
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        for post_id in post_list:
            task = asyncio.create_task(
                self.get_comments(post_id, semaphore), name=post_id)
            task_list.append(task)
        if len(task_list) > 0:
            await asyncio.wait(task_list)

    async def get_comments(self, post_id: str, semaphore: asyncio.Semaphore) -> None:
        async with semaphore:
            try:
                # 将关键词列表传递给 get_post_all_comments 方法
                await self.toutiao_client.get_post_all_comments(
                    post_id=post_id,
                    crawl_interval=random.random(),
                    is_fetch_sub_comments=config.ENABLE_GET_SUB_COMMENTS,
                    callback=toutiao_store.batch_update_posts_comments,
                    max_count=config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES
                )
                utils.logger.info(
                    f"[ToutiaoCrawler.get_comments] post_id: {post_id} comments have all been obtained and filtered ...")
            except DataFetchError as e:
                utils.logger.error(
                    f"[ToutiaoCrawler.get_comments] post_id: {post_id} get comments failed, error: {e}")

    async def get_creators_and_posts(self) -> None:
        """
        Get the information and posts of the specified creator
        """
        utils.logger.info("[ToutiaoCrawler.get_creators_and_posts] Begin get toutiao creators")
        for token in config.TOUTIAO_CREATOR_ID_LIST:
            # 获取账号信息
            creator_info = await self.get_creator_info(token)
            await toutiao_store.save_creator(token, creator_info)

            # Get all post information of the creator
            all_post_list = await self.toutiao_client.get_all_user_posts(
                token=token,
                count_limit=config.COUNT_LIMIT,
                # callback=self.fetch_creator_post_detail 不需要获取详情，因为文章列表里的信息已经足够
                callback=None
            )

            for post_item in all_post_list:
                if post_item is not None:
                    # utils.logger.info(f"[ToutiaoCrawler.get_creators_and_posts] update post_item={post_item}")
                    await toutiao_store.update_toutiao_post(post_item)

            post_ids = [post_item.get("id") for post_item in all_post_list]
            await self.batch_get_note_comments(post_ids)


    async def get_creator_info(self, token: str) -> Dict:
        """
        获取用户信息
        （未找到相关API，采用解析账号主页的方式获取信息）
        """
        creator_profile_url = f"https://www.toutiao.com/c/user/token/{token}/"

        creator_profile_page = await self.browser_context.new_page()
        await creator_profile_page.goto(creator_profile_url)
        name = ''  # 账号名称
        like_count = 0  # 获赞数
        fans_count = 0  # 粉丝数
        follow_count = 0  # 关注数
        desc = ''  # 简介
        try:
            # 检查账号信息元素是否加载成功
            await creator_profile_page.wait_for_selector(selector='.detail', timeout=1000 * 5)

            name = await creator_profile_page.locator(".name").text_content()
            desc = (await creator_profile_page.locator(".user-desc").text_content()).replace('简介：', "")  # 简介

            for stat_item in await creator_profile_page.locator(".stat-item").all():
                stat_text = await stat_item.text_content()
                stat_num = await stat_item.locator(".num").text_content()
                if '获赞' in stat_text:
                    like_count = stat_num
                elif '粉丝' in stat_text:
                    fans_count = stat_num
                elif '关注' in stat_text:
                    follow_count = stat_num
                utils.logger.info(f"get_creator_info: stat_text={stat_text} stat_num={stat_num}")

            utils.logger.info(f"get_creator_info: name={name} like_count={like_count} fans_count={fans_count} "
                              f"follow_count={follow_count} desc={desc}")
        except Exception as e:
            utils.logger.error(f"get_creator_info: {e}")
        finally:
            await creator_profile_page.close()

        return {
            'token': token,
            'name': name,
            'like_count': like_count,
            'fans_count': fans_count,
            'follow_count': follow_count,
            'desc': desc,
        }

    @staticmethod
    def format_proxy_info(ip_proxy_info: IpInfoModel) -> Tuple[Optional[Dict], Optional[Dict]]:
        """format proxy info for playwright and httpx"""
        playwright_proxy = {
            "server": f"{ip_proxy_info.protocol}{ip_proxy_info.ip}:{ip_proxy_info.port}",
            "username": ip_proxy_info.user,
            "password": ip_proxy_info.password,
        }
        httpx_proxy = {
            f"{ip_proxy_info.protocol}": f"http://{ip_proxy_info.user}:{ip_proxy_info.password}@{ip_proxy_info.ip}:{ip_proxy_info.port}"
        }
        return playwright_proxy, httpx_proxy

    async def create_toutiao_client(self, httpx_proxy: Optional[str]) -> ToutiaoClient:
        """Create toutiao client"""
        cookie_str, cookie_dict = utils.convert_cookies(await self.browser_context.cookies())  # type: ignore
        toutiao_client = ToutiaoClient(
            proxies=httpx_proxy,
            headers={
                "User-Agent": await self.context_page.evaluate("() => navigator.userAgent"),
                "Cookie": cookie_str,
                "Host": "www.toutiao.com",
                "Origin": "https://www.toutiao.com/",
                "Referer": "https://www.toutiao.com/",
                "Content-Type": "application/json;charset=UTF-8"
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
        )
        return toutiao_client

    async def launch_browser(
            self,
            chromium: BrowserType,
            playwright_proxy: Optional[Dict],
            user_agent: Optional[str],
            headless: bool = True
    ) -> BrowserContext:
        """Launch browser and create browser context"""
        if config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(os.getcwd(), "browser_data",
                                         config.USER_DATA_DIR % config.PLATFORM)  # type: ignore
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,  # type: ignore
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent
            )  # type: ignore
            return browser_context
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy)  # type: ignore
            browser_context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent
            )
            return browser_context

    async def close(self) -> None:
        """Close browser context"""
        await self.browser_context.close()
        utils.logger.info("[ToutiaoCrawler.close] Browser context closed ...")
