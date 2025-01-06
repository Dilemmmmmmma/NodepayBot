import asyncio
import time

from utils.network import get_profile_info, ping_all_accounts
from utils.services import get_proxy_choice, assign_proxies
from utils.services import processed_tokens, load_tokens, send_request
from utils.settings import ACTIVATE_ACCOUNTS, DAILY_CLAIM, logger, Fore
from utils.settings import DOMAIN_API, CONNECTION_STATES, setup_logging, startup_art


cleaning_up = False

# Account class to hold token, proxy, and other details for each account
class AccountData:
    def __init__(self, token, index, proxy=None):
        self.token = token
        self.index = index
        self.proxy = proxy

        # Set the initial connection status to 'None' (no connection)
        self.status_connect = CONNECTION_STATES["NONE_CONNECTION"]
        self.points_per_proxy = {}
        self.account_info = {}
        self.claimed_rewards = set()
        self.retries = 0
        self.last_ping_status = 'Waiting...'

        # Initialize a list to hold browser session details (such as ping counts and scores)
        self.browser_ids = [
            {
                'ping_count': 0,
                'successful_pings': 0,
                'score': 0,
                'start_time': time.time(),
                'last_ping_time': None
            }
        ]

    # Reset account state for retries or disconnection
    def reset(self):
        self.status_connect = CONNECTION_STATES["NONE_CONNECTION"]
        self.account_info = {}
        self.retries = 3
        logger.info(f"{Fore.CYAN}00{Fore.RESET} - {Fore.GREEN}正在重置账户 {self.index}{Fore.RESET}")

# Activate accounts and update their status
async def activate_accounts(accounts) -> None:
    if isinstance(accounts, AccountData):
        accounts = [accounts]

    tasks = [send_request(DOMAIN_API["ACTIVATE"], {}, account, method="POST") for account in accounts]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    for account, response in zip(accounts, responses):
        if isinstance(response, Exception):
            logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}激活账户 {account.index} 时出错: {response}{Fore.RESET}")
            account.status_connect = CONNECTION_STATES["NONE_CONNECTION"]
            continue

        if response and response.get("code") == 5 and "already activated" in response.get("msg", "").lower():
            account.status_connect = CONNECTION_STATES["CONNECTED"]
            logger.debug(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.GREEN}账户 {account.index} 已激活{Fore.RESET}")

        elif response and response.get("success") and response.get("data") is True:
            account.status_connect = CONNECTION_STATES["CONNECTED"]
            logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.GREEN}账户 {account.index} 激活成功{Fore.RESET}")

# Synchronize account data by fetching profile and earning information
async def process_account(account):
    try:
        await get_profile_info(account)
    except Exception as e:
        logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}处理账户 {account.index} 时出错: {e}{Fore.RESET}")

# Handles resource cleanup during interruptions
async def clean_up_resources():
    global cleaning_up
    if cleaning_up:
        return
    
    cleaning_up = True

    for task in asyncio.all_tasks():
        if not task.done():
            task.cancel()
    
    try:
        await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass

    logger.info(f"{Fore.CYAN}00{Fore.RESET} - {Fore.GREEN}清理完成{Fore.RESET}")

# Main function to manage the application flow
async def process():
    try:
        startup_art()
        setup_logging()

        proxies = get_proxy_choice()
        tokens = await load_tokens()

        logger.info(f"{Fore.CYAN}00{Fore.RESET} - {'正在使用代理...' if proxies else '未使用代理...'}")

        token_proxy_pairs = assign_proxies(tokens, proxies)
        accounts = [AccountData(token, index, proxy) for index, (token, proxy) in enumerate(token_proxy_pairs, start=1)]

        if ACTIVATE_ACCOUNTS:
            await activate_accounts(accounts)

        while True:
            try:
                if DAILY_CLAIM:
                    processed_tokens.clear()
                    logger.info(f"{Fore.CYAN}00{Fore.RESET} - 正在加载账户详情，检查奖励并领取。请稍候...")
                    await asyncio.sleep(3)

                    tasks = [asyncio.create_task(process_account(account)) for account in accounts]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for result in results:
                        if isinstance(result, Exception):
                            logger.error(f"{Fore.CYAN}00{Fore.RESET} - {Fore.RED}处理账户时出错: {result}{Fore.RESET}")

                logger.info(f"{Fore.CYAN}00{Fore.RESET} - 准备发送 ping 请求，请稍候...")
                await asyncio.sleep(3)

                await ping_all_accounts(accounts)

            except Exception as e:
                logger.error(f"{Fore.CYAN}00{Fore.RESET} - {Fore.RED}主循环中出现意外错误: {e}{Fore.RESET}")

    except asyncio.CancelledError:
        logger.info(f"{Fore.CYAN}00{Fore.RESET} - {Fore.RED}进程中断，正在清理...{Fore.RESET}")
    finally:
        logger.info(f"{Fore.CYAN}00{Fore.RESET} - 正在释放所有资源...")
        await clean_up_resources()
