import os
import socket
import logging
from typing import Optional

logger = logging.getLogger("astrbot")

try:
    import socks  # PySocks提供的SOCKS代理功能
except ImportError:
    socks = None  # 如果未安装PySocks，则设为None

class ProxyManager:
    """代理管理类，负责处理HTTP和SOCKS代理的设置和清除"""
    
    def __init__(self):
        # 保存原始socket类，用于本地连接检测和恢复
        self.original_socket = socket.socket
        # 记录当前代理状态
        self.current_proxy = None
        self.is_socks_proxy = False
    
    def setup_proxy(self, proxy_url: Optional[str]) -> bool:
        """
        根据提供的代理URL设置代理
        
        Args:
            proxy_url: 代理URL，格式为 'http://host:port' 或 'socks5://host:port'
                      如果为None或空字符串，则清除代理
        
        Returns:
            bool: 代理设置是否成功
        """
        # 首先清除所有现有代理设置
        self.clear_proxy()
        
        # 如果没有提供代理URL，直接返回True
        if not proxy_url:
            logger.info("未配置代理，使用直接连接")
            return True
            
        self.current_proxy = proxy_url
        
        # 检查是否是SOCKS代理
        if proxy_url.startswith('socks'):
            return self._setup_socks_proxy(proxy_url)
        else:
            return self._setup_http_proxy(proxy_url)
    
    def _setup_socks_proxy(self, proxy_url: str) -> bool:
        """设置SOCKS代理"""
        if socks is None:
            logger.warning("检测到SOCKS代理配置，但未正确安装PySocks。请使用 pip install pysocks")
            return False
            
        try:
            proxy_parts = proxy_url.split('://')
            if len(proxy_parts) != 2:
                logger.error(f"代理URL格式错误: {proxy_url}")
                return False
                
            proxy_type_str, proxy_addr = proxy_parts
            # 确定代理类型
            if proxy_type_str == 'socks5':
                proxy_type = socks.SOCKS5
            elif proxy_type_str == 'socks4':
                proxy_type = socks.SOCKS4
            else:
                proxy_type = socks.SOCKS5
                logger.warning(f"未知的SOCKS类型: {proxy_type_str}，默认使用SOCKS5")
            
            # 解析代理地址和端口
            if ':' in proxy_addr:
                proxy_host, proxy_port_str = proxy_addr.split(':')
                try:
                    proxy_port = int(proxy_port_str)
                    # 设置默认socket为SOCKS代理
                    socks.set_default_proxy(proxy_type, proxy_host, proxy_port)
                    socket.socket = socks.socksocket
                    self.is_socks_proxy = True
                    
                    # 同时设置环境变量以支持不使用PySocks的库
                    os.environ["ALL_PROXY"] = proxy_url
                    logger.info(f"已设置SOCKS{proxy_type_str[-1]}代理: {proxy_host}:{proxy_port}")
                    return True
                except ValueError:
                    logger.error(f"代理端口无效: {proxy_port_str}")
                    return False
            else:
                logger.error(f"代理地址格式错误: {proxy_addr}")
                return False
        except Exception as e:
            logger.error(f"设置SOCKS代理时出错: {e}")
            return False
    
    def _setup_http_proxy(self, proxy_url: str) -> bool:
        """设置HTTP代理"""
        try:
            # HTTP代理设置
            os.environ["HTTP_PROXY"] = proxy_url
            os.environ["HTTPS_PROXY"] = proxy_url
            os.environ["http_proxy"] = proxy_url
            os.environ["https_proxy"] = proxy_url
            logger.info(f"已设置HTTP/HTTPS代理: {proxy_url}")
            return True
        except Exception as e:
            logger.error(f"设置HTTP代理时出错: {e}")
            return False
    
    def clear_proxy(self) -> None:
        """清除所有代理设置"""
        # 清除环境变量
        self._clear_proxy_env()
        
        # 如果之前设置了SOCKS代理，恢复原始socket
        if self.is_socks_proxy:
            socket.socket = self.original_socket
            self.is_socks_proxy = False
            logger.info("已清除SOCKS代理设置")
        
        self.current_proxy = None
    
    def _clear_proxy_env(self) -> None:
        """清除所有代理相关的环境变量"""
        proxy_env_vars = [
            "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"
        ]
        for var in proxy_env_vars:
            if var in os.environ:
                del os.environ[var]
    
    def get_current_proxy(self) -> Optional[str]:
        """获取当前使用的代理URL"""
        return self.current_proxy
    
    def is_using_proxy(self) -> bool:
        """检查是否正在使用代理"""
        return self.current_proxy is not None
    
    def setup_no_proxy_hosts(self, hosts: list = None) -> None:
        """设置不使用代理的主机列表"""
        if hosts is None:
            hosts = ["localhost", "127.0.0.1", "::1", "0.0.0.0"]
        
        os.environ["no_proxy"] = ",".join(hosts)
        
    def get_direct_socket(self):
        """返回未经代理的原始socket类，用于本地连接检测"""
        return self.original_socket