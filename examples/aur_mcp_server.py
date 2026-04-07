import aiohttp
import asyncio
from datetime import datetime
import json
from mcp.server.fastmcp import FastMCP

# 初始化 FastMCP 服务器
mcp = FastMCP("ArchLinux-Pkg-Search")

async def process_aur_info_response(task_coro):
    try:
        resp = await task_coro
        resp.raise_for_status()
        data = await resp.json()
        if isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
             return data
        else:
             return None
    except Exception:
        return None

@mcp.tool()
async def search_pkg(pkg_name: str, repo: str = None) -> str:
    """
    搜索 Arch Linux 官方仓库和 AUR 的软件包。
    
    Args:
        pkg_name: 要搜索的包名 (例如 linux, yay)
        repo: 可选，指定官方仓库 (例如 core, extra)
    """
    if repo:
        repo = repo[0].upper() + repo[1:]

    timeout = aiohttp.ClientTimeout(total=10)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        # 1. 首先尝试搜索官方仓库
        search_url = f"https://archlinux.org/packages/search/json/?name={pkg_name}"
        if repo:
            search_url += f"&repo={repo}"

        try:
            async with session.get(search_url) as resp:
                resp.raise_for_status()
                data = await resp.json()
                results = data.get("results", [])

                if results:
                    result = results[0]
                    last_update_str = "N/A"
                    if result.get("last_update"):
                        try:
                            dt_obj = datetime.fromisoformat(result["last_update"].replace("Z", "+00:00"))
                            last_update_str = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            last_update_str = result.get('last_update', 'N/A').replace("T", " ").replace("Z", "")

                    msg = (
                        f"仓库：{result.get('repo', 'N/A')}
"
                        f"包名：{result.get('pkgname', 'N/A')}
"
                        f"版本：{result.get('pkgver', 'N/A')}
"
                        f"描述：{result.get('pkgdesc', 'N/A')}
"
                        f"打包：{result.get('packager', 'N/A')}
"
                        f"上游：{result.get('url', 'N/A')}
"
                        f"更新日期：{last_update_str}"
                    )
                    return msg

        except Exception as e:
            pass # 官方仓库失败则继续查 AUR

        # 2. 尝试 AUR
        aur_suggest_url = f"https://aur.archlinux.org/rpc/v5/suggest/{pkg_name}"
        suggestions = []
        try:
            async with session.get(aur_suggest_url) as resp:
                resp.raise_for_status()
                suggestions = await resp.json()
                if not isinstance(suggestions, list):
                     suggestions = []
        except Exception:
            pass

        if not suggestions:
             suggestions = [pkg_name]

        aur_info_base_url = "https://aur.archlinux.org/rpc/v5/info/"
        target_pkg_info = None

        if len(suggestions) == 1 or suggestions[0] == pkg_name:
            target_name = suggestions[0]
            aur_info_url = f"{aur_info_base_url}{target_name}"
            try:
                async with session.get(aur_info_url) as resp:
                     resp.raise_for_status()
                     search_map = await resp.json()
                     if search_map.get("results") and isinstance(search_map["results"], list) and len(search_map["results"]) > 0:
                         target_pkg_info = search_map["results"][0]
            except Exception:
                 pass
        else:
            fetch_tasks = []
            for suggestion in suggestions:
                 fetch_tasks.append(process_aur_info_response(session.get(f"{aur_info_base_url}{suggestion}")))

            aur_responses = await asyncio.gather(*fetch_tasks)

            best_result = None
            max_votes = -1.0

            for result_data in aur_responses:
                 if isinstance(result_data, Exception) or result_data is None:
                      continue

                 if result_data.get("results"):
                     pkg_info = result_data["results"][0]
                     try:
                         votes = float(pkg_info.get("NumVotes", 0.0) or 0.0)
                     except (ValueError, TypeError):
                         votes = 0.0
                     if votes > max_votes:
                         max_votes = votes
                         best_result = pkg_info

            if best_result:
                target_pkg_info = best_result

        # 3. 格式化并返回 AUR 结果
        if target_pkg_info:
            maintainer = target_pkg_info.get("Maintainer") or "孤儿包"
            out_of_date_ts = target_pkg_info.get("OutOfDate")
            out_of_date_str = ""
            if out_of_date_ts:
                try:
                    out_of_date_dt = datetime.fromtimestamp(float(out_of_date_ts))
                    out_of_date_str = f"过期时间：{out_of_date_dt.strftime('%Y-%m-%d %H:%M:%S')}
"
                except (ValueError, TypeError, OSError):
                     pass

            upstream_url = target_pkg_info.get("URL") or "无"
            co_maintainers = target_pkg_info.get("CoMaintainers") or []
            co_maintainers_str = ""
            if co_maintainers and isinstance(co_maintainers, list):
                 co_maintainers_str = f" ( {' '.join(map(str, co_maintainers))} )"

            last_modified_ts = target_pkg_info.get("LastModified")
            last_modified_str = "N/A"
            if last_modified_ts:
                try:
                     last_modified_dt = datetime.fromtimestamp(float(last_modified_ts))
                     last_modified_str = last_modified_dt.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError, OSError):
                     pass

            num_votes = 0.0
            try:
                num_votes = float(target_pkg_info.get("NumVotes", 0.0) or 0.0)
            except (ValueError, TypeError):
                pass

            pkg_display_name = target_pkg_info.get('Name', 'N/A')

            msg = (
                 f"仓库：AUR
"
                 f"包名：{pkg_display_name}
"
                 f"版本：{target_pkg_info.get('Version', 'N/A')}
"
                 f"描述：{target_pkg_info.get('Description', 'N/A')}
"
                 f"维护者：{maintainer}{co_maintainers_str}
"
                 f"上游：{upstream_url}
"
                 f"{out_of_date_str}"
                 f"更新时间：{last_modified_str}
"
                 f"投票：{num_votes:.0f}
"
                 f"AUR 链接：https://aur.archlinux.org/packages/{pkg_display_name}"
             )
            return msg

        return f"没有在官方仓库或 AUR 中找到名为 '{pkg_name}' 的相关软件。"

if __name__ == "__main__":
    # 以 stdio 模式运行 MCP 服务器
    mcp.run(transport='stdio')
