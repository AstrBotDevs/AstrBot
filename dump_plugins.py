import urllib.request
import json

# --- 配置 ---
REPO_OWNER = "AstrBotDevs"
REPO_NAME = "AstrBot"
START_ISSUE_NUMBER = 970
LABEL_TO_FIND = "plugin-publish"
OUTPUT_FILENAME = "plugin_publish_issues.txt"
ISSUE_STATE = "closed"  # 只筛选状态为 closed 的 Issue


def fetch_and_format_issues(
    repo_owner, repo_name, start_issue_number, label_name, output_file, issue_state
):
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues?state={issue_state}&labels={label_name}&sort=created&direction=asc&per_page=100"
    headers = {"Accept": "application/vnd.github+json"}
    found_issues = []
    page = 1

    while True:
        request_url = f"{api_url}&page={page}"
        request = urllib.request.Request(request_url, headers=headers)
        try:
            with urllib.request.urlopen(request) as response:
                data = json.loads(response.read().decode("utf-8"))
                if not data:
                    break  # 没有更多 Issues 了

                for issue in data:
                    issue_number = issue.get("number")
                    if issue_number is not None and issue_number >= start_issue_number:
                        title = issue.get("title", "No Title")
                        author = issue.get("user", {}).get("login", "Unknown")
                        found_issues.append(f"{title} by @{author} in #{issue_number}")

                # 检查是否有下一页
                if "Link" in response.headers:
                    links = response.headers["Link"].split(",")
                    next_page_exists = False
                    for link in links:
                        if 'rel="next"' in link:
                            next_page_exists = True
                            break
                    if not next_page_exists:
                        break
                    page += 1
                else:
                    break  # 没有 Link header，假设没有更多页了

        except urllib.error.HTTPError as e:
            print(f"HTTP Error: {e.code} - {e.reason}")
            return
        except urllib.error.URLError as e:
            print(f"URL Error: {e.reason}")
            return
        except json.JSONDecodeError:
            print("Error decoding JSON response.")
            return

    if found_issues:
        with open(output_file, "w", encoding="utf-8") as f:
            for line in found_issues:
                f.write(line + "\n")
        print(
            f"已找到 {len(found_issues)} 个状态为 '{issue_state}'，带有 '{label_name}' 标签且 Issue Number 大于等于 {start_issue_number} 的 Issues，并已保存到 '{output_file}'。"
        )
    else:
        print(
            f"未找到任何状态为 '{issue_state}'，带有 '{label_name}' 标签且 Issue Number 大于等于 {start_issue_number} 的 Issues。"
        )


if __name__ == "__main__":
    fetch_and_format_issues(
        REPO_OWNER,
        REPO_NAME,
        START_ISSUE_NUMBER,
        LABEL_TO_FIND,
        OUTPUT_FILENAME,
        ISSUE_STATE,
    )
