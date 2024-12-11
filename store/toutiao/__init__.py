# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：  
# 1. 不得用于任何商业用途。  
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。  
# 3. 不得进行大规模爬取或对平台造成运营干扰。  
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。   
# 5. 不得用于任何非法或不当的用途。
#   
# 详细许可条款请参阅项目根目录下的LICENSE文件。  
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。  


# -*- coding: utf-8 -*-
# @Author  : relakkes@gmail.com
# @Time    : 2024/1/14 18:46
# @Desc    :
from typing import List

import config
from var import source_keyword_var

from .toutiao_store_impl import *


class ToutiaoStoreFactory:
    STORES = {
        "csv": ToutiaoCsvStoreImplement,
        "db": ToutiaoDbStoreImplement,
        "json": ToutiaoJsonStoreImplement
    }

    @staticmethod
    def create_store() -> AbstractStore:
        store_class = ToutiaoStoreFactory.STORES.get(config.SAVE_DATA_OPTION)
        if not store_class:
            raise ValueError(
                "[ToutiaoStoreFactory.create_store] Invalid save option only supported csv or db or json ...")
        return store_class()


async def update_toutiao_post(post_item: Dict):
    save_content_item = {}

    cell_type = post_item.get("cell_type")
    if cell_type == 32:  # 微头条
        user_info = post_item.get("user")
        user_id = source = ""
        if user_info:
            user_id = user_info.get("user_id", "")
            source = user_info.get("name", "")
        save_content_item = {
            "id": post_item.get("id", ""),
            "source": source,
            "user_id": user_id,
            "is_original": False,  # 无此字段
            "read_count": post_item.get("read_count", 0),
            "like_count": post_item.get("digg_count", 0),
            "comment_count": post_item.get("comment_count", 0),
            "publish_time": post_item.get("publish_time", ""),
            "title": post_item.get("rich_content"),
            "abstract": "",  # 无此字段
            "url": post_item.get("share_url", ""),
        }

    elif cell_type == 0:  # 视频
        user_info = post_item.get("user_info")
        user_id = ''
        if user_info:
            user_id = user_info.get("user_id", "")
        action = post_item.get("action", {})
        save_content_item = {
            "id": post_item.get("id", ""),
            "source": post_item.get("source", ""),
            "user_id": user_id,
            "is_original": False,  # 无此字段
            "read_count": action.get("read_count", 0),
            "like_count": action.get("digg_count", 0),
            "comment_count": post_item.get("comment_count", 0),
            "publish_time": post_item.get("publish_time", ""),
            "title": post_item.get("title", ""),
            "abstract": "", # 无此字段
            "url": post_item.get("display_url", ""),
        }

    elif cell_type == 60:  # 普通文章
        user_info = post_item.get("user_info")
        user_id = ''
        if user_info:
            user_id = user_info.get("user_id", "")
        save_content_item = {
            "id": post_item.get("id", ""),
            "source": post_item.get("source", ""),
            "user_id": user_id,
            "is_original": post_item.get("is_original", False),
            "read_count": post_item.get("read_count", 0),
            "like_count": post_item.get("like_count", 0),
            "comment_count": post_item.get("comment_count", 0),
            "publish_time": post_item.get("publish_time", ""),
            "title": post_item.get("title", ""),
            "abstract": post_item.get("abstract", ""),
            "url": post_item.get("url", ""),
        }

    utils.logger.info(
        f"[store.update_toutiao_post] post id:{save_content_item.get('id')}, "
        f"title:{save_content_item.get('title')}")
    await ToutiaoStoreFactory.create_store().store_content(content_item=save_content_item)


async def batch_update_posts_comments(aweme_id: str, comments: List[Dict]):
    if not comments:
        return
    for comment_item in comments:
        await update_post_comment(aweme_id, comment_item)


async def update_post_comment(post_id: str, comment_item: Dict):
    # utils.logger.info(f"[store.toutiao.update_post_comment] id={post_id}, comment={comment_item}")

    save_comment_item = {
        "id": comment_item.get("id", 0),
        "post_id": post_id,
        "user_id": comment_item.get("user_id", ""),
        "user_name": comment_item.get("user_name", ""),
        "create_time": comment_item.get("create_time", 0),
        "publish_loc_info": comment_item.get("publish_loc_info", ""),
        "text": comment_item.get("text", ""),
        "score": comment_item.get("score", 0),
    }
    utils.logger.info(
        f"[store.toutiao.update_post_comment] toutiao post comment: {save_comment_item.get('id')}, content: {save_comment_item.get('text')}")

    await ToutiaoStoreFactory.create_store().store_comment(comment_item=save_comment_item)


async def save_creator(user_id: str, user_info: Dict):
    utils.logger.info(f"save_creator: user_id={user_id} , user_info={user_info}")
    local_db_item = {
        'token': user_info.get('token'),
        'name': user_info.get('name'),
        'like_count': user_info.get('like_count'),
        'fans_count': user_info.get('fans_count'),
        'follow_count': user_info.get('follow_count'),
        'desc': user_info.get('desc'),
    }

    utils.logger.info(f"[store.toutiao.save_creator] creator:{local_db_item}")
    await ToutiaoStoreFactory.create_store().store_creator(local_db_item)
