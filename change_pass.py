import time
from contextlib import closing
import paramiko
import logging
import argparse
import configparser
import getpass
from functools import partial, partialmethod
import asyncio
import pprint

def configure_logger(config:dict):
    logging.CHANEL_DIALOG = 11
    logging.addLevelName(logging.CHANEL_DIALOG, "CHANEL_DIALOG")
    logging.Logger.chanel_dialog = partialmethod(logging.Logger.log, logging.CHANEL_DIALOG)
    logging.chanel_dialog = partial(logging.log, logging.CHANEL_DIALOG)

    logging_level = logging.INFO
    if config["log_level"]["level"] == "debug":
        logging_level = logging.DEBUG
    
    elif config["log_level"]["level"] == "chanel_dialog":
        logging_level = logging.CHANEL_DIALOG
    
    logging.basicConfig(level=logging_level, format="%(asctime)s %(levelname)s %(message)s")


def display_colored_log_message(message, log_level=logging.DEBUG):
    # https://misc.flogisoft.com/bash/tip_colors_and_formatting
    reset  = "\x1b[0m"
    red    = "\x1b[38;5;196m"
    green  = "\x1b[32m"
    yellow = "\x1b[38;5;3m"
    purple = "\x1b[38;5;93m"
    orange = "\x1b[38;5;208m"
    
    if log_level == logging.DEBUG:
        logging.debug(message)
        return

    if log_level == logging.INFO:
        logging.info(f"{green}{message}{reset}")
        return

    if log_level == logging.WARNING:
        logging.warning(f"{yellow}{message}{reset}")
        return

    if log_level == logging.ERROR:
        logging.error(f"{red}{message}{reset}")
        return

    if log_level == logging.CRITICAL:
        logging.critical(f"{orange}{message}{reset}")
        return
    
    if log_level == logging.CHANEL_DIALOG:
        logging.chanel_dialog(f"{purple}{message}{reset}")
        return


def create_parser():
    parser     = argparse.ArgumentParser(description="")
    subparsers = parser.add_subparsers(help="sub-command help", dest="command")

    parser_interractive      = subparsers.add_parser("interractive", help="Will display a prompt for ssh_username, current_password and new_password")
    parser_interractive.add_argument("machines_inventory_path", help="Path to machine inventory, machine name must separate by comma")
    parser_interractive.add_argument("--input_list", action="store_true", help="Force machines_inventory_path to be an list like none interractive mode")

    parser_none_interractive = subparsers.add_parser("noneInterractive", help="More convienant to be integrate in other script") 
    parser_none_interractive.add_argument("ssh_username", help="Username for connection")
    parser_none_interractive.add_argument("current_password", help="Current password for connection")
    parser_none_interractive.add_argument("new_password", help="new password to set")
    parser_none_interractive.add_argument("machines_list", help="List of machine must separate by comma")

    return parser.parse_args()


def interactive_mode_gatherer_information() -> tuple:
    ssh_username = input("username > ")
    print("Don't worry password input is not display in prompt")
    old_ssh_pass = getpass.getpass(f"Current ssh password for user {ssh_username} > ")
    new_pass     = getpass.getpass(f"New password ssh for user {ssh_username} > ")
    
    return ssh_username, old_ssh_pass, new_pass 


def interactive_mode_get_machines(input_list_mode:bool, machines) -> list[str]:
    
    if(input_list_mode):
        return machines.split(MACHINE_SEPARATOR)

    with open(machines, "r") as file: data = file.read()
    return data.split(MACHINE_SEPARATOR)


def one_of_patterns_are_matche(patterns:str, string:str) -> bool:
    if len(string) < 5: return False
    display_colored_log_message(string, logging.CHANEL_DIALOG)

    for pattern in patterns: 
        if string.find(pattern) != -1: return True

    return False


def wait_until_one_of_patterns_matche(channel, patterns:"str", timeout_in_seconds:int=15):
    patterns = patterns.lower().split(CONFIG_SPLIT_SEPARATOR)
    display_colored_log_message(f"{patterns=}")

    trigger_timeout = time.time() + timeout_in_seconds

    
    while True:
        channel_read_buffer = ""
        if channel.recv_ready(): channel_read_buffer = channel.recv(4096).decode("utf-8").lower()
        if channel_read_buffer != "" and one_of_patterns_are_matche(patterns, channel_read_buffer): break
        if  time.time() > trigger_timeout: raise TimeoutError(f"Timeout while waiting for '{patterns}' on the channel")


def change_expired_password_over_ssh(host:str, username:str, current_password:str, new_password:str, patterns:dict):
    """Changes expired password over SSH with paramiko"""
    display_colored_log_message(f"Start changing password for {host}", logging.INFO)
    with closing(paramiko.SSHClient()) as ssh_connection:
        ssh_connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_connection.connect(hostname=host, username=username, password=current_password)
        ssh_channel = ssh_connection.invoke_shell()

        wait_until_one_of_patterns_matche(ssh_channel, patterns["patterns"]["attempt_pattern_prompt1"])       
        ssh_channel.send(f'{current_password}\n')

        wait_until_one_of_patterns_matche(ssh_channel, patterns["patterns"]["attempt_pattern_prompt2"])
        ssh_channel.send(f'{new_password}\n')

        wait_until_one_of_patterns_matche(ssh_channel, patterns["patterns"]["attempt_pattern_prompt3"])
        ssh_channel.send(f'{new_password}\n')

        wait_until_one_of_patterns_matche(ssh_channel, patterns["patterns"]["attempt_pattern_prompt4"])



async def async_change_expired_password_over_ssh(host:str, username:str, current_password:str, new_password:str, patterns:dict) -> tuple:
    try:
        await asyncio.to_thread(change_expired_password_over_ssh,host=host, username=username, current_password=current_password, new_password=new_password, patterns=patterns)
    except Exception as e:
        return (host, "failed", e)

    return (host, "sucess", None)

MACHINE_SEPARATOR       = ","
CONFIG_SPLIT_SEPARATOR  = ","

async def main(): 
    config = configparser.ConfigParser()
    config.read('config.ini')
    configure_logger(config)

    args = create_parser()
    if not args.command:
        display_colored_log_message("No subcommande used see help with change_pass -h", logging.CRITICAL)
        exit()

    ssh_username     = "" 
    current_ssh_pass = "" 
    new_pass         = ""
    machines         = []

    if args.command == "interractive":
        
        ssh_username, current_ssh_pass, new_pass = interactive_mode_gatherer_information()
        machines = interactive_mode_get_machines(args.input_list, args.machines_inventory_path)

    elif args.command == "noneInterractive":
        ssh_username     = args.ssh_username
        current_ssh_pass = args.current_password
        new_pass         = args.new_password
        machines         = args.machines_list.split(MACHINE_SEPARATOR) 

    display_colored_log_message(f"{ssh_username=}")
    display_colored_log_message(f"{current_ssh_pass=}")
    display_colored_log_message(f"{new_pass=}")
    display_colored_log_message(f"{machines=}")
    
    functions = [async_change_expired_password_over_ssh(host=machine, 
                                                        username=ssh_username, 
                                                        current_password=current_ssh_pass, 
                                                        new_password=new_pass, 
                                                        patterns=config 
                                                        ) for machine in machines]
           
    results = await asyncio.gather(*functions)
    
    failed = []
    sucess = []
    for result in results:
        if result[1] == "sucess":
            sucess.append(result)
        else:
            failed.append(result)
    
    display_colored_log_message(pprint.pformat(sucess), logging.INFO)
    display_colored_log_message(pprint.pformat(failed), logging.ERROR)


asyncio.run(main())
