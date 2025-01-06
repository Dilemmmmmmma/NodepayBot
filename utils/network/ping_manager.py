import asyncio
import time

from colorama import Style
from urllib.parse import urlparse

from utils.services import retry_request, mask_token, resolve_ip
from utils.settings import DOMAIN_API, PING_DURATION, PING_INTERVAL, logger, Fore


# 发送周期性ping请求到服务器
async def process_ping_response(response, url, account, data):
    if not response or not isinstance(response, dict):
        logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}无效或为空的响应: {response}{Fore.RESET}")
        return "failed", None

    response_data = response.get("data", {})
    if not isinstance(response_data, dict):
        logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}响应中缺少 'data' 字段: {response_data}{Fore.RESET}")
        return "failed", None

    logger.debug(
        f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - 响应 {{"
        f"成功: {response.get('success')}, 代码: {response.get('code')}, "
        f"IP得分: {response.get('data', {}).get('ip_score', 'N/A')}, "
        f"消息: {response.get('msg', '无消息')}}}"
    )

    try:
        version = response_data.get("version", "2.2.7")
        data["version"] = version

        ping_result = "成功" if response.get("code", -1) == 0 else "失败"
        network_quality = response_data.get("ip_score", "N/A")

        account_stats = account.browser_ids[0]
        account_stats.setdefault("ping_count", 0)
        account_stats.setdefault("score", 0)
        account_stats.setdefault("successful_pings", 0)

        account_stats['ping_count'] += 1
        if ping_result == "成功":
            account_stats['score'] += 10
            account_stats["successful_pings"] += 1
        else:
            account_stats['score'] -= 5

        logger.debug(
            f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - "
            f"浏览器统计 {{Ping次数: {account.browser_ids[0]['ping_count']}, "
            f"成功次数: {account.browser_ids[0]['successful_pings']}, "
            f"分数: {account.browser_ids[0]['score']}, "
            f"最后Ping时间: {account.browser_ids[0]['last_ping_time']:.2f}}}"
        )

        return ping_result, network_quality

    except (AttributeError, KeyError, TypeError) as e:
        short_error = str(e).split(". See")[0]
        logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}处理响应时出错: {short_error}{Fore.RESET}")
        return "failed", None

# 启动每个账户的ping过程
async def start_ping(account):
    current_time = time.time()

    separator_line = f"{Fore.CYAN + Style.BRIGHT}-" * 75 + f"{Style.RESET_ALL}"

    if account.index == 1:
        logger.debug(separator_line)

    # 验证browser_ids
    if not account.browser_ids or not isinstance(account.browser_ids[0], dict):
        logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}无效或缺失browser_ids结构{Fore.RESET}")
        return

    account.browser_ids[0].setdefault('ping_count', 0)
    account.browser_ids[0].setdefault('score', 0)

    last_ping_time = account.browser_ids[0].get('last_ping_time', 0)
    logger.debug(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - 当前时间: {current_time}, 上次ping时间: {last_ping_time}")

    if last_ping_time and (current_time - last_ping_time) < PING_INTERVAL:
        logger.warning(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.YELLOW}稍等一下！请稍后再尝试{Fore.RESET}")
        return

    account.browser_ids[0]['last_ping_time'] = current_time

    # 开始ping循环
    for url in DOMAIN_API.get("PING", []):
        try:
            logger.debug(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - 正在发送ping到 {urlparse(url).path}")
            data = {
                "id": account.account_info.get("uid"),
                "browser_id": account.browser_ids[0],
                "timestamp": int(time.time()),
            }

            # 发送请求并处理重试
            response = await retry_request(url, data, account)
            if response is None:
                continue
        
            ping_result, network_quality = await process_ping_response(response, url, account, data)

            logger.debug(separator_line)

            identifier = await resolve_ip(account)
            logger.info(
                f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - "
                f"{Fore.GREEN if ping_result == '成功' else Fore.RED}Ping {ping_result}{Fore.RESET}, "
                f"Token: {Fore.CYAN}{mask_token(account.token)}{Fore.RESET}, "
                f"IP得分: {Fore.CYAN}{network_quality}{Fore.RESET}, "
                f"{'代理' if account.proxy else 'IP地址'}: {Fore.CYAN}{identifier}{Fore.RESET}"
            )

            if ping_result == "成功":
                break

        except KeyError as ke:
            logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}Ping过程中发生KeyError: {ke}{Fore.RESET}")

# 定期ping所有账户
async def ping_all_accounts(accounts):
    start_time = time.time()

    while time.time() - start_time < PING_DURATION:
        try:
            # 并发ping所有账户
            tasks = [start_ping(account) for account in accounts]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 记录ping失败的账户
            for account, result in zip(accounts, results):
                if isinstance(result, Exception):
                    logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}Ping账户时出错: {result}{Fore.RESET}")

        except Exception as e:
            short_error = str(e).split(". See")[0]
            logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}ping_all_accounts中出现意外错误: {short_error}{Fore.RESET}")

        logger.info(f"{Fore.CYAN}00{Fore.RESET} - 睡眠 {PING_INTERVAL} 秒后开始下一轮")
        await asyncio.sleep(PING_INTERVAL)
