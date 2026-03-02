"""Provider/Model/Key 管理命令 - astr provider / astr model / astr key"""

import click

from ..connection import send_message
from ..output import output_response


@click.command(help="查看/切换 Provider")
@click.argument("index", default="", required=False)
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def provider(index: str, use_json: bool) -> None:
    """查看/切换 Provider

    \b
    示例:
      astr provider           查看当前 Provider 列表
      astr provider 1         切换到 Provider 1
    """
    cmd = "/provider" if not index else f"/provider {index}"
    response = send_message(cmd)
    output_response(response, use_json)


@click.command(help="查看/切换模型")
@click.argument("index_or_name", default="", required=False)
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def model(index_or_name: str, use_json: bool) -> None:
    """查看/切换模型

    \b
    示例:
      astr model              查看当前模型列表
      astr model 1            切换到模型 1
      astr model gpt-4        按名称切换模型
    """
    cmd = "/model" if not index_or_name else f"/model {index_or_name}"
    response = send_message(cmd)
    output_response(response, use_json)


@click.command(help="查看/切换 Key")
@click.argument("index", default="", required=False)
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def key(index: str, use_json: bool) -> None:
    """查看/切换 Key

    \b
    示例:
      astr key                查看当前 Key 列表
      astr key 1              切换到 Key 1
    """
    cmd = "/key" if not index else f"/key {index}"
    response = send_message(cmd)
    output_response(response, use_json)
