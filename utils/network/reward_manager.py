from colorama import Style
from datetime import timedelta

from utils.settings import DOMAIN_API, logger, Fore
from utils.services import retry_request, mark_token, mask_token

# Function to display account information
def display_account_info(account, data):
    logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.LIGHTMAGENTA_EX}账户信息 {data['name']}{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - 邮箱: {Fore.CYAN}{data['email']}{Fore.RESET}")
    logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - 推荐链接: {Fore.CYAN}{data['referral_link']}{Fore.RESET}")
    logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - 状态: {Fore.CYAN}{data['state']}{Fore.RESET}")
    logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - 网络收益率: {Fore.CYAN}{data['network_earning_rate']}{Fore.RESET}")

# Function to display earning information
def display_earning_info(account, data):
    logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.LIGHTMAGENTA_EX}{data['season_name']} 状态{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - 总收益: {Fore.CYAN}{data['total_earning']}{Fore.RESET}")
    logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - 今日收益: {Fore.CYAN}{data['today_earning']}{Fore.RESET}")
    logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - 当前积分: {Fore.CYAN}{data['current_point']}{Fore.RESET}")
    logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - 待处理积分: {Fore.CYAN}{data['pending_point']}{Fore.RESET}")

# Function to get reward mapping
def get_reward_mapping():
    return {
        "1": {"name": "每日", "required": None, "is_progress_based": False},
        "19": {"name": "每小时", "required": None, "is_progress_based": True},
        "15": {"name": "7天", "required": None, "is_progress_based": False},
        "16": {"name": "14天", "required": "7天", "is_progress_based": False},
        "17": {"name": "21天", "required": "14天", "is_progress_based": False},
        "18": {"name": "28天", "required": "21天", "is_progress_based": False}
    }

# Fetch and display profile information for the account
async def get_profile_info(account):
    try:
        # Check if the token is already processed
        if not await mark_token(account):
            logger.debug(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.YELLOW}Token 已经处理过，跳过此账户...{Fore.RESET}")
            return

        # Log separator for better readability
        separator_line = f"{Fore.CYAN + Style.BRIGHT}-" * 75 + f"{Style.RESET_ALL}"

        if account.index == 1:
            logger.info(separator_line)

        # Fetch account profile details
        logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - 正在使用 Token: {Fore.CYAN}{mask_token(account.token)}{Fore.RESET} 获取账户资料")
        response = await retry_request(DOMAIN_API["SESSION"], {}, account)

        if response.get("success"):
            logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - 账户资料获取{Fore.GREEN}成功{Fore.RESET}")
            account.account_info = response["data"]
            data = account.account_info

            # Display account info
            logger.info(separator_line)
            display_account_info(account, data)

            if account.account_info.get("uid"):
                await get_earning_info(account)
                await process_and_claim_rewards(account)

            logger.info(separator_line)

        else:
            logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}会话失败，Token:{Fore.RESET} "
                         f"{Fore.CYAN}{mask_token(account.token)}{Fore.RESET}")

    except Exception as e:
        logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}获取账户资料失败，Token:{Fore.RESET} "
                     f"{Fore.CYAN}{mask_token(account.token)}{Fore.RESET} ")

        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}响应内容:{Fore.RESET} {e.response.text}")

# Fetch and display the earning information of an account
async def get_earning_info(account):
    try:
        response = await retry_request(DOMAIN_API["EARN_INFO"], {}, account, method="GET")

        if not response or not response.get('success'):
            logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}无法获取收益信息，响应:{Fore.RESET} {response}")
            return

        data = response.get('data', {})
        if not isinstance(data, dict):
            logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}收益信息数据结构无效{Fore.RESET}")
            return

        # Display earning information using the new function
        display_earning_info(account, data)

    except Exception as e:
        logger.error(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}获取收益信息失败:{Fore.RESET} {e}")

# Handle checking and claiming rewards for an account
async def process_and_claim_rewards(account):
    try:
        response = await retry_request(DOMAIN_API["MISSION"], {}, account, method="GET")

        if not response.get('success'):
            logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}无法获取任务数据:{Fore.RESET} {response}")
            return

        data = response.get('data', [])

        if not data:
            logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.YELLOW}此账户没有任务{Fore.RESET}")
            return

        logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.LIGHTMAGENTA_EX}正在检查 {account.index} 账户的奖励{Style.RESET_ALL}")

        # Get the reward mapping from the new function
        reward_mapping = get_reward_mapping()

        for item in data:
            reward_info = reward_mapping.get(str(item['id']))
            if reward_info:
                if reward_info["required"] and reward_info["required"] not in account.claimed_rewards:
                    continue
                await claim_reward(account, item, reward_info["name"], reward_info["required"], reward_info["is_progress_based"])

    except Exception as e:
        logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}检查奖励时发生错误:{Fore.RESET} {e}")

# Handle the process of claiming daily rewards for an account
async def claim_reward(account, reward_data, reward_name, required_claim=None, is_progress_based=False):
    current_process = reward_data.get('current_process', 0)
    target_process = reward_data.get('target_process', 1)

    # Handle rewards based on progress or availability
    if is_progress_based and current_process < target_process:
        logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.YELLOW}{reward_name} 进度不足，无法领取。进度: {current_process}/{target_process}{Fore.RESET}")
        return

    # Reward available for claiming
    if reward_data.get('status') == "AVAILABLE":
        logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.GREEN}{reward_name} 奖励可领取{Fore.RESET}")
        await complete_reward_claim(account, reward_data['id'], reward_name)
        account.claimed_rewards.add(reward_name.replace(" ", "-"))

    # Reward locked, handle locked and progress-based cases
    elif reward_data.get('status') == "LOCK":
        if current_process < target_process:
            logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.YELLOW}{reward_name} 被锁定，进度: {current_process}/{target_process}{Fore.RESET}")

        elif current_process == target_process:
            logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.GREEN}{reward_name} 完成，锁定，正在过渡{Fore.RESET}")
            # Optionally try to claim again or mark it as ready

        else:
            remain_time = int(reward_data.get('remain_time', 0)) / 1000
            time_remaining = str(timedelta(seconds=remain_time)).split('.')[0]
            logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.YELLOW}{reward_name} 将在... {time_remaining} 后可领取{Fore.RESET}")

    # Reward will be available soon (handle unanticipated or specific statuses)
    elif reward_data.get('status') in ["SOON", "PENDING", "WAITING"]:
        remain_time = int(reward_data.get('remain_time', 0)) / 1000
        time_remaining = str(timedelta(seconds=remain_time)).split('.')[0]
        logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.YELLOW}{reward_name} 将在... {time_remaining} 后可领取{Fore.RESET}")

    # Handle rewards that are already completed
    elif reward_data.get('status') == "COMPLETED":
        logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.GREEN}{reward_name} 奖励已完成并领取{Fore.RESET}")
        account.claimed_rewards.add(reward_name.replace(" ", "-"))

    else:
        logger.warning(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}未处理状态 '{reward_data.get('status')}' 对于 {reward_name}.{Fore.RESET}")

# Finalize the reward claim and print the results
async def complete_reward_claim(account, mission_id, reward_type):
    try:
        data = {"mission_id": str(mission_id)}

        response = await retry_request(DOMAIN_API["COMPLETE_MISSION"], data, account)

        # Handle the response based on success
        if response.get('success'):
            earned_points = response['data']['earned_points']
            logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.GREEN}{reward_type} 奖励领取成功:{Fore.RESET} {Fore.CYAN}{earned_points} 积分{Fore.RESET}")

        else:
            logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}领取 {reward_type} 奖励失败:{Fore.RESET} {Fore.RED}{response}{Fore.RESET}")

    except Exception as e:
        logger.info(f"{Fore.CYAN}{account.index:02d}{Fore.RESET} - {Fore.RED}领取 {reward_type} 奖励时发生错误:{Fore.RESET} {Fore.RED}{e}{Fore.RESET}")
