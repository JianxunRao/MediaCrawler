#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Trojx(饶建勋) on 2024/12/4

# 头条账号首页
# https://www.toutiao.com/c/user/token/MS4wLjABAAAAjlhp9frdJMzX1sj23-gKqPXE11NMJ0HejjFa3kG44spBlt4xL6f7wZTiYW_zTXH6/

import asyncio
import copy
import json
import sys
import urllib.parse
from typing import Any, Callable, Dict, Optional

import requests
from playwright.async_api import BrowserContext

from base.base_crawler import AbstractApiClient
from tools import utils
from var import request_keyword_var

from .exception import *
from .field import *
from .help import *


class ToutiaoClient(AbstractApiClient):
    def __init__(
            self,
            timeout=30,
            proxies=None,
            *,
            headers: Dict,
            playwright_page: Optional[Page],
            cookie_dict: Dict
    ):
        self.proxies = proxies
        self.timeout = timeout
        self.headers = headers
        self._host = "https://www.toutiao.com"
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict

    async def __process_req_params(
            self, uri: str, params: Optional[Dict] = None, headers: Optional[Dict] = None,
            request_method="GET"
    ):

        if not params:
            return
        headers = headers or self.headers
        local_storage: Dict = await self.playwright_page.evaluate("() => window.localStorage")  # type: ignore
        # utils.logger.info(f"__process_req_params: local_storage={local_storage}")
        common_params = {
            "app_name": "toutiao_web",
            "msToken": local_storage.get("xmst"),
        }
        params.update(common_params)
        query_string = urllib.parse.urlencode(params)

        # 20240927 a-bogus更新（JS版本）
        post_data = {}
        if request_method == "POST":
            post_data = params
        a_bogus = await get_a_bogus(uri, query_string, post_data, headers["User-Agent"], self.playwright_page)
        params["a_bogus"] = a_bogus

    async def request(self, method, url, **kwargs):
        utils.logger.debug(f"request: method={method} url={url}")
        response = None
        if method == "GET":
            response = requests.request(method, url, **kwargs)
        elif method == "POST":
            response = requests.request(method, url, **kwargs)
        try:
            if response.text == "" or response.text == "blocked":
                utils.logger.error(f"request params incrr, response.text: {response.text}")
                raise Exception("account blocked")
            return response.json()
        except Exception as e:
            raise DataFetchError(f"{e}, {response.text}")

    async def get(self, uri: str, params: Optional[Dict] = None, headers: Optional[Dict] = None):
        """
        GET请求
        """
        await self.__process_req_params(uri, params, headers)
        headers = headers or self.headers
        return await self.request(method="GET", url=f"{self._host}{uri}", params=params, headers=headers)

    async def post(self, uri: str, data: dict, headers: Optional[Dict] = None):
        await self.__process_req_params(uri, data, headers)
        headers = headers or self.headers
        return await self.request(method="POST", url=f"{self._host}{uri}", data=data, headers=headers)

    async def pong(self, browser_context: BrowserContext) -> bool:
        # local_storage = await self.playwright_page.evaluate("() => window.localStorage")
        # if local_storage.get("HasUserLogin", "") == "1":
        #     return True
        #
        # _, cookie_dict = utils.convert_cookies(await browser_context.cookies())
        # return cookie_dict.get("LOGIN_STATUS") == "1"
        # 默认已经登录，目前看是否登录不影响接口查询
        return True

    async def update_cookies(self, browser_context: BrowserContext):
        cookie_str, cookie_dict = utils.convert_cookies(await browser_context.cookies())
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    async def search_info_by_keyword(
            self,
            keyword: str,
            offset: int = 0,
            search_channel: SearchChannelType = SearchChannelType.GENERAL,
            sort_type: SearchSortType = SearchSortType.GENERAL,
            publish_time: PublishTimeType = PublishTimeType.UNLIMITED,
            search_id: str = ""
    ):
        raise Exception("not implemented.")

    async def get_post_by_id(self, id: str) -> Any:
        """
        Toutiao post Detail API
        :param id:
        :return:
        """
        raise Exception("not implemented.")

    async def get_post_comments(self, id: str, offset: int = 0):
        """get note comments

        """
        uri = "/article/v4/tab_comments/"
        params = {
            "aid": 24,
            "offset": offset,
            "count": 20,
            "group_id": id,
            "item_id": id,
        }
        return await self.get(uri, params)

    async def get_sub_comments(self, comment_id: str, cursor: int = 0):
        """
        获取子评论
        从网页上看，头条似乎并没有子评论。接口中的子评论列表也是空的
        """
        raise Exception("not supported")

    async def get_post_all_comments(
            self,
            post_id: str,
            crawl_interval: float = 1.0,
            is_fetch_sub_comments=False,
            callback: Optional[Callable] = None,
            max_count: int = 10,
    ):
        """
        获取帖子的所有评论，包括子评论
        :param post_id: 帖子ID
        :param crawl_interval: 抓取间隔
        :param is_fetch_sub_comments: 是否抓取子评论
        :param callback: 回调函数，用于处理抓取到的评论
        :param max_count: 一次帖子爬取的最大评论数量
        :return: 评论列表
        """
        result = []
        comments_has_more = 1
        comments_cursor = 0
        while comments_has_more and len(result) < max_count:
            comments_res = await self.get_post_comments(post_id, comments_cursor)
            # utils.logger.info(f"get_post_all_comments: comments_res={comments_res}")

            comments_has_more = comments_res.get("has_more", 0)

            comments_cursor = comments_res.get("offset", 0)
            comments_data = comments_res.get("data", [])
            if not comments_data:
                continue
            comments = []
            for comment_item in comments_data:
                comments.append(comment_item.get("comment", {}))

            if len(result) + len(comments) > max_count:
                comments = comments[:max_count - len(result)]
            result.extend(comments)

            if callback:  # 如果有回调函数，就执行回调函数
                await callback(post_id, comments)

            await asyncio.sleep(crawl_interval)

            if not is_fetch_sub_comments:
                continue
            utils.logger.warn(f"get_post_all_comments: fetch_sub_comments not supported.")

        # utils.logger.info(f"get_post_all_comments: result={result}")
        return result

    async def get_user_posts(self, token: str, max_behot_time: str = "0") -> Dict:
        """
        获取用户文章
        """

        uri = "/api/pc/list/user/feed"
        params = {
            "category": "profile_all",
            "token": token,
            "max_behot_time": max_behot_time,
            "aid": 24,
        }
        return await self.get(uri, params)

    async def get_all_user_posts(self, token: str, count_limit: int = sys.maxsize, callback: Optional[Callable] = None):
        """
        获取用户全部文章
        """
        posts_has_more = 1
        max_behot_time = "0"
        result = []
        retry_times = 0
        while posts_has_more == 1 and retry_times <= 5 and len(result) < count_limit:
            post_res = await self.get_user_posts(token, max_behot_time)

            # 由于今日头条的反爬虫机制，有时会获取到空的数据，所以需要用try来控制，一般比例是3：1所以是访问3次有一次获得数据
            try:
                max_behot_time = post_res['next']['max_behot_time']  # 数据为空就没有这个选项从而引发try
            except Exception as e:
                retry_times += 1
                utils.logger.error(f"get_all_user_posts: retry_times={retry_times} error={e}")
                continue

            utils.logger.debug('get_all_user_posts：%s' % str(post_res))
            retry_times = 0
            posts_has_more = post_res['has_more']  # 获取是否还有下一页数据

            post_list = post_res.get("data") if post_res.get("data") else []
            utils.logger.info(
                f"[ToutiaoClient.get_all_user_posts] got token:{token} list len : {len(post_list)}")
            # utils.logger.info(f"[ToutiaoClient.get_all_user_posts] post_list={post_list}")
            if callback:
                await callback(post_list)
            result.extend(post_list)
        return result
