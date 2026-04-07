from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import aiohttp
import asyncio
from datetime import datetime
import json

# 辅助函数，用于安全地处理来自 asyncio.gather 的 AUR 信息响应
async def process_aur_info_response(task_coro):

    try:
        # 等待 aiohttp 请求协程
        resp = await task_coro
        # 检查响应状态，如果响应是 4xx 或 5xx，则抛出 HTTPError
        resp.raise_for_status()
        # 将响应内容解析为 JSON
        data = await resp.json()
        # 确保即使 API 返回意外的数据结构，我们也能返回有用的信息
        if isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
             return data
        else:
             # 记录警告日志，返回 None
             logger.warning(f"意外的 AUR 信息响应结构: {data}")
             return None # 或者抛出自定义错误
    except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
        # 记录警告日志，返回异常对象
        logger.warning(f"处理一个 AUR 信息请求时失败: {e}")
        return e # 返回异常对象以便后续过滤
    except Exception as e: # 捕获意外错误
        # 记录错误日志，包含堆栈跟踪，返回异常对象
        logger.error(f"处理 AUR 信息请求时发生意外错误: {e}", exc_info=True)
        return e


@register("pkg", "liyp", "一个查询Archlinux包信息插件", "0.0.1")
class PkgPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("pkg")
    async def search_pkg(self, event: AstrMessageEvent):
        '''搜索 Arch Linux 官方仓库和 AUR 的软件包. 使用方法: pkg <packagename> [repo]'''
        args = event.message_str.split()
        if len(args) < 2:
            yield event.plain_result("请输入包名,例如,pkg linux [core]")
            return

        pkg_name = args[1]
        repo = None
        if len(args) > 2 and args[2]:
            # 正确化 repo 的首字母大写（例如，core -> Core, extra -> Extra）

            repo = args[2][0].upper() + args[2][1:]

        timeout = aiohttp.ClientTimeout(total=10) # 超时时间

        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 1. 首先尝试搜索官方仓库
            search_url = f"https://archlinux.org/packages/search/json/?name={pkg_name}"
            if repo:
                search_url += f"&repo={repo}"

            logger.debug(f"Pkg search URL: {search_url}")

            try:
                async with session.get(search_url) as resp:
                    resp.raise_for_status() # 检查 HTTP 错误（4xx, 5xx）
                    data = await resp.json()
                    results = data.get("results", [])

                    if results:
                        # 在官方仓库中找到结果，格式化并返回第一个结果
                        result = results[0]
                        # 格式化时间戳
                        last_update_str = "N/A"
                        if result.get("last_update"):
                            try:
                                # 尝试解析 ISO 8601 格式
                                dt_obj = datetime.fromisoformat(result["last_update"].replace("Z", "+00:00"))
                                last_update_str = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                logger.warning(f"无法解析官方仓库的时间戳: {result.get('last_update')}")
                                # 如果解析失败，回退到原始字符串
                                last_update_str = result.get('last_update', 'N/A').replace("T", " ").replace("Z", "")

                        msg = (
                            f"仓库：{result.get('repo', 'N/A')}\n"
                            f"包名：{result.get('pkgname', 'N/A')}\n"
                            f"版本：{result.get('pkgver', 'N/A')}\n"
                            f"描述：{result.get('pkgdesc', 'N/A')}\n"
                            f"打包：{result.get('packager', 'N/A')}\n"
                            f"上游：{result.get('url', 'N/A')}\n"
                            f"更新日期：{last_update_str}"
                        )
                        yield event.plain_result(msg)
                        return # 找到结果，结束

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"获取官方仓库包信息时出错: '{pkg_name}': {e}")
                yield event.plain_result(f"查询官方仓库时网络错误或超时！")
                return # 网络错误，不继续搜索 AUR
            except json.JSONDecodeError as e:
                 logger.error(f"解析官方仓库搜索的 JSON 时出错: '{pkg_name}': {e}")
                 yield event.plain_result("无法解析官方仓库的响应！")
                 return
            except Exception as e: # 捕获处理过程中的其他错误
                logger.error(f"处理官方仓库数据时出错: '{pkg_name}': {e}", exc_info=True)
                yield event.plain_result("处理官方仓库数据时出错！")
                return

            # 2. 如果在官方仓库中未找到（或搜索失败但决定继续），尝试 AUR
            logger.info(f"Package '{pkg_name}' not found in official repos (or specified repo '{repo}'). Checking AUR.")

            # 2a. 从 AUR 获取建议
            aur_suggest_url = f"https://aur.archlinux.org/rpc/v5/suggest/{pkg_name}"
            logger.debug(f"AUR suggest URL: {aur_suggest_url}")
            suggestions = []
            try:
                async with session.get(aur_suggest_url) as resp:
                    resp.raise_for_status()
                    # suggest 端点返回一个简单的字符串列表
                    suggestions = await resp.json()
                    if not isinstance(suggestions, list):
                         logger.error(f"意外的 AUR 建议响应类型: {type(suggestions)}")
                         suggestions = [] # 视为没有建议

            except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
                logger.error(f"获取或解析 AUR 建议时出错: '{pkg_name}': {e}")
                # 不在这里抛出错误，意味着无法使用建议
            except Exception as e:
                logger.error(f"AUR 建议期间发生意外错误: '{pkg_name}': {e}", exc_info=True)

            if not suggestions:
                 # 即使建议失败或返回为空，尝试直接信息查找
                 logger.info(f"没有 AUR 建议 for '{pkg_name}'，尝试直接信息查找。")
                 suggestions = [pkg_name] # 假设原始名称是唯一的建议

            # 2b. 获取建议的信息并找到最佳匹配
            aur_info_base_url = "https://aur.archlinux.org/rpc/v5/info/"
            target_pkg_info = None

            if len(suggestions) == 1 or suggestions[0] == pkg_name:
                # 只有一个建议（或直接匹配），直接获取其信息
                target_name = suggestions[0]
                aur_info_url = f"{aur_info_base_url}{target_name}"
                logger.debug(f"AUR 单个/直接信息 URL: {aur_info_url}")
                try:
                    async with session.get(aur_info_url) as resp:
                         resp.raise_for_status()
                         search_map = await resp.json()
                         if search_map.get("results") and isinstance(search_map["results"], list) and len(search_map["results"]) > 0:
                             target_pkg_info = search_map["results"][0]
                         else:
                             logger.info(f"AUR 信息查找 for '{target_name}' 返回无结果。")
                except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
                     logger.error(f"获取或解析单个 AUR 信息时出错: '{target_name}': {e}")
                except Exception as e:
                     logger.error(f"获取单个 AUR 信息时发生意外错误: '{target_name}': {e}", exc_info=True)

            else:
                # 多个建议：并发获取所有建议的信息，选择投票数最高的
                logger.info(f"找到多个 AUR 建议 ({len(suggestions)})，获取所有信息...")
                fetch_tasks = []
                # 为每个建议创建获取信息的任务
                for suggestion in suggestions:
                     fetch_tasks.append(process_aur_info_response(session.get(f"{aur_info_base_url}{suggestion}")))

                # 并发运行所有获取任务
                aur_responses = await asyncio.gather(*fetch_tasks)

                best_result = None
                max_votes = -1.0 # 使用 -1 确保即使只有一个包投票数为 0 也会被选中

                for result_data in aur_responses:
                     # 跳过处理过程中出现错误或 None 的结果
                     if isinstance(result_data, Exception) or result_data is None:
                          continue

                     # Go 代码假设 'results' 总是至少有一个项目。更安全的做法是检查。
                     if result_data.get("results"):
                         # API 返回一个列表，即使对于单个包信息请求也是如此
                         pkg_info = result_data["results"][0]
                         # 安全获取 NumVotes，默认为 0.0 如果缺失或不是数字
                         try:
                             votes = float(pkg_info.get("NumVotes", 0.0) or 0.0)
                         except (ValueError, TypeError):
                             votes = 0.0
                         if votes > max_votes:
                             max_votes = votes
                             best_result = pkg_info

                if best_result:
                    target_pkg_info = best_result
                else:
                    logger.info(f"无法根据建议确定最佳 AUR 包 for '{pkg_name}'。")

            # 3. 格式化并返回 AUR 结果（如果找到）
            if target_pkg_info:
                maintainer = target_pkg_info.get("Maintainer") or "孤儿包"
                out_of_date_ts = target_pkg_info.get("OutOfDate") # Unix 时间戳（float 或 int）或 None
                out_of_date_str = ""
                if out_of_date_ts:
                    try:
                        out_of_date_dt = datetime.fromtimestamp(float(out_of_date_ts))
                        out_of_date_str = f"过期时间：{out_of_date_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    except (ValueError, TypeError, OSError):
                         logger.warning(f"无效的 AUR OutOfDate 时间戳: {out_of_date_ts}")

                upstream_url = target_pkg_info.get("URL") or "无"
                # CoMaintainers 可能缺失或为 None，默认为空列表
                co_maintainers = target_pkg_info.get("CoMaintainers") or []
                co_maintainers_str = ""
                if co_maintainers and isinstance(co_maintainers, list):
                     # 确保元素是字符串后再连接
                     co_maintainers_str = f" ( {' '.join(map(str, co_maintainers))} )"

                last_modified_ts = target_pkg_info.get("LastModified")
                last_modified_str = "N/A"
                if last_modified_ts:
                    try:
                         last_modified_dt = datetime.fromtimestamp(float(last_modified_ts))
                         last_modified_str = last_modified_dt.strftime('%Y-%m-%d %H:%M:%S')
                    except (ValueError, TypeError, OSError):
                         logger.warning(f"无效的 AUR LastModified 时间戳: {last_modified_ts}")

                num_votes = 0.0
                try:
                    num_votes = float(target_pkg_info.get("NumVotes", 0.0) or 0.0)
                except (ValueError, TypeError):
                    pass # 保持 num_votes 为 0.0

                pkg_display_name = target_pkg_info.get('Name', 'N/A')

                msg = (
                     f"仓库：AUR\n"
                     f"包名：{pkg_display_name}\n"
                     f"版本：{target_pkg_info.get('Version', 'N/A')}\n"
                     f"描述：{target_pkg_info.get('Description', 'N/A')}\n"
                     f"维护者：{maintainer}{co_maintainers_str}\n"
                     f"上游：{upstream_url}\n"
                     f"{out_of_date_str}" # 仅在时间戳有效时包含此行
                     f"更新时间：{last_modified_str}\n"
                     f"投票：{num_votes:.0f}\n" # 将浮点数格式化为整数字符串
                     f"AUR 链接：https://aur.archlinux.org/packages/{pkg_display_name}"
                 )
                yield event.plain_result(msg)
                return

            # 4. 如果在官方仓库或 AUR 中未找到
            yield event.plain_result(f"没有在官方仓库或 AUR 中找到名为 '{pkg_name}' 的相关软件。")
    async def terminate(self):
        '''可选：清理资源，例如在 __init__ 中创建的持久化 ClientSession。'''
        logger.info("PkgPlugin 正在终止。")
        # 如果你在 __init__ 中创建了 self.session，请在这里关闭它：
        # if hasattr(self, 'session') and self.session:
        #     await self.session.close()
