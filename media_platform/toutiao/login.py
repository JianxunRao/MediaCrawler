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
import functools
import sys
from typing import Optional

from playwright.async_api import BrowserContext, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from tenacity import (RetryError, retry, retry_if_result, stop_after_attempt,
                      wait_fixed)

import config
from base.base_crawler import AbstractLogin
from cache.cache_factory import CacheFactory
from tools import utils


class ToutiaoLogin(AbstractLogin):

    def __init__(self,
                 login_type: str,
                 browser_context: BrowserContext,  # type: ignore
                 context_page: Page,  # type: ignore
                 login_phone: Optional[str] = "",
                 cookie_str: Optional[str] = ""
                 ):
        config.LOGIN_TYPE = login_type
        self.browser_context = browser_context
        self.context_page = context_page
        self.login_phone = login_phone
        self.scan_qrcode_time = 60
        self.cookie_str = cookie_str

    async def begin(self):
        """
            Start login toutiao website
            滑块中间页面的验证准确率不太OK... 如果没有特俗要求，建议不开抖音登录，或者使用cookies登录
        """

        # popup login dialog
        await self.popup_login_dialog()

        # select login type
        if config.LOGIN_TYPE == "qrcode":
            await self.login_by_qrcode()
        elif config.LOGIN_TYPE == "phone":
            raise ValueError("[ToutiaoLogin.begin] 未实现")
        elif config.LOGIN_TYPE == "cookie":
            await self.login_by_cookies()
        else:
            raise ValueError(
                "[ToutiaoLogin.begin] Invalid Login Type Currently only supported qrcode or phone or cookie ...")

        # 如果页面重定向到滑动验证码页面，需要再次滑动滑块
        await asyncio.sleep(6)

        # check login state
        utils.logger.info(f"[ToutiaoLogin.begin] login finished then check login state ...")
        try:
            await self.check_login_state()
        except RetryError:
            utils.logger.info("[ToutiaoLogin.begin] login failed please confirm ...")
            sys.exit()

        # wait for redirect
        wait_redirect_seconds = 5
        utils.logger.info(
            f"[ToutiaoLogin.begin] Login successful then wait for {wait_redirect_seconds} seconds redirect ...")
        await asyncio.sleep(wait_redirect_seconds)

    @retry(stop=stop_after_attempt(600), wait=wait_fixed(1), retry=retry_if_result(lambda value: value is False))
    async def check_login_state(self):
        """Check if the current login status is successful and return True otherwise return False"""
        current_cookie = await self.browser_context.cookies()
        _, cookie_dict = utils.convert_cookies(current_cookie)
        utils.logger.info(f"[ToutiaoLogin] check_login_state: cookie_dict={cookie_dict}")

        for page in self.browser_context.pages:
            try:
                local_storage = await page.evaluate("() => window.localStorage")
                utils.logger.info(f"[ToutiaoLogin] check_login_state: local_storage={local_storage}")
                if local_storage.get("HasUserLogin", "") == "1":
                    return True
            except Exception as e:
                utils.logger.warn(f"[ToutiaoLogin] check_login_state waring: {e}")
                await asyncio.sleep(0.1)

        if cookie_dict.get("LOGIN_STATUS") == "1":
            return True

        return False

    async def popup_login_dialog(self):
        """If the login dialog box does not pop up automatically, we will manually click the login button"""
        dialog_selector = ".ttp-modal"
        try:
            # check dialog box is auto popup and wait for 10 seconds
            await self.context_page.wait_for_selector(dialog_selector, timeout=1000 * 5)
        except Exception as e:
            utils.logger.error(
                f"[ToutiaoLogin.popup_login_dialog] login dialog box does not pop up automatically, error: {e}")
            utils.logger.info(
                "[ToutiaoLogin.popup_login_dialog] login dialog box does not pop up automatically, we will manually click the login button")
            login_button_ele = self.context_page.locator(".login-button").get_by_text("立即登录")
            await login_button_ele.click()
            await asyncio.sleep(0.5)

    async def login_by_qrcode(self):
        utils.logger.info("[ToutiaoLogin.login_by_qrcode] Begin login toutiao by qrcode...")
        qrcode_img_selector = ".web-login-scan-code__content__qrcode-wrapper__qrcode"
        base64_qrcode_img = await utils.find_login_qrcode(
            self.context_page,
            selector=qrcode_img_selector
        )
        if not base64_qrcode_img:
            utils.logger.info("[ToutiaoLogin.login_by_qrcode] login qrcode not found please confirm ...")
            sys.exit()

        partial_show_qrcode = functools.partial(utils.show_qrcode, base64_qrcode_img)
        asyncio.get_running_loop().run_in_executor(executor=None, func=partial_show_qrcode)
        await asyncio.sleep(2)

    async def login_by_cookies(self):
        utils.logger.info("[ToutiaoLogin.login_by_cookies] Begin login toutiao by cookie ...")
        for key, value in utils.convert_str_cookie_to_dict(self.cookie_str).items():
            await self.browser_context.add_cookies([{
                'name': key,
                'value': value,
                'domain': ".toutiao.com",
                'path': "/"
            }])

    async def login_by_mobile(self):
        utils.logger.info("[ToutiaoLogin.login_by_mobile] Begin login toutiao by cookie ...")
        raise Exception("Not supported.")
